use std::sync::Mutex;
use std::time::{Duration, Instant};
use tauri::{Manager, RunEvent};
use tauri_plugin_shell::process::{CommandChild, CommandEvent};
use tauri_plugin_shell::ShellExt;

struct SidecarChild(Mutex<Option<CommandChild>>);

/// How long the sidecar gets to exit on its own before we force-kill it.
const SHUTDOWN_GRACE: Duration = Duration::from_secs(3);

/// Ask the sidecar to exit on its own.
///
/// The sidecar is a PyInstaller onefile bundle: the process we spawned is the bootloader, and the
/// actual server runs in a child of it. Only a polite signal makes the bootloader take that child
/// down and delete its extraction directory. A hard kill leaves the server running (still holding
/// port 3001, so the next launch never becomes ready) plus a few hundred MB of temp files behind.
#[cfg(unix)]
fn request_shutdown(pid: u32) {
    unsafe {
        libc::kill(pid as libc::pid_t, libc::SIGTERM);
    }
}

#[cfg(unix)]
fn is_running(pid: u32) -> bool {
    // The shell plugin waits on the child from its own thread, so an exited sidecar is reaped
    // promptly and stops answering signal 0.
    unsafe { libc::kill(pid as libc::pid_t, 0) == 0 }
}

#[cfg(windows)]
fn request_shutdown(pid: u32) {
    // Windows has no SIGTERM. `taskkill /T` takes the bootloader down together with the Python
    // child it spawned, which is the process that would otherwise be left holding port 3001.
    use std::os::windows::process::CommandExt;
    const CREATE_NO_WINDOW: u32 = 0x0800_0000;
    let _ = std::process::Command::new("taskkill")
        .args(["/PID", &pid.to_string(), "/T", "/F"])
        .creation_flags(CREATE_NO_WINDOW)
        .status();
}

#[cfg(windows)]
fn is_running(_pid: u32) -> bool {
    // taskkill returns once the tree is gone, so there is nothing left to wait for.
    false
}

fn shutdown_sidecar(app: &tauri::AppHandle) {
    let Some(state) = app.try_state::<SidecarChild>() else {
        return;
    };
    let Ok(mut guard) = state.0.lock() else {
        return;
    };
    let Some(child) = guard.take() else {
        return;
    };

    let pid = child.pid();
    request_shutdown(pid);

    let deadline = Instant::now() + SHUTDOWN_GRACE;
    while Instant::now() < deadline {
        if !is_running(pid) {
            println!("Sidecar exited cleanly");
            return;
        }
        std::thread::sleep(Duration::from_millis(50));
    }

    eprintln!("Sidecar did not exit within {SHUTDOWN_GRACE:?}, forcing it");
    let _ = child.kill();
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let app = tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_dialog::init())
        .setup(|app| {
            // Hide main window until API is ready
            let window = app.get_webview_window("main").unwrap();
            window.hide().unwrap();

            let sidecar_command = app
                .shell()
                .sidecar("alembic-api")
                .expect("failed to create sidecar command");
            let (mut rx, child) = sidecar_command.spawn().expect("failed to spawn sidecar");

            // Store child handle for shutdown
            app.manage(SidecarChild(Mutex::new(Some(child))));

            // Log sidecar stdout/stderr
            tauri::async_runtime::spawn(async move {
                while let Some(event) = rx.recv().await {
                    match event {
                        CommandEvent::Stdout(line) => {
                            println!("API: {}", String::from_utf8_lossy(&line));
                        }
                        CommandEvent::Stderr(line) => {
                            eprintln!("API ERR: {}", String::from_utf8_lossy(&line));
                        }
                        _ => {}
                    }
                }
            });

            // Poll health endpoint, then show window
            let window_clone = window.clone();
            tauri::async_runtime::spawn(async move {
                let client = reqwest::Client::new();
                let mut ready = false;
                for _ in 0..50 {
                    // 50 * 200ms = 10s timeout
                    match client.get("http://localhost:3001/").send().await {
                        Ok(resp) if resp.status().is_success() => {
                            ready = true;
                            break;
                        }
                        _ => {}
                    }
                    tokio::time::sleep(std::time::Duration::from_millis(200)).await;
                }
                if ready {
                    println!("API ready, showing window");
                    let _ = window_clone
                        .eval("if (typeof loadOverview === 'function') loadOverview();");
                } else {
                    eprintln!("API failed to become ready within 10s, showing window anyway");
                }
                let _ = window_clone.show();
            });

            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building tauri application");

    // Shut the sidecar down on the way out, not on window destruction: quitting from the menu or
    // the dock never destroys a window, and on macOS a destroyed window does not end the app.
    app.run(|app_handle, event| {
        if let RunEvent::Exit = event {
            shutdown_sidecar(app_handle);
        }
    });
}
