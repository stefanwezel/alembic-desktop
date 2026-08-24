use std::sync::Mutex;
use std::time::{Duration, Instant};
use tauri::{Manager, RunEvent};
use tauri_plugin_shell::process::{CommandChild, CommandEvent};
use tauri_plugin_shell::ShellExt;

struct SidecarChild(Mutex<Option<CommandChild>>);

/// How long the sidecar gets to exit on its own before we force-kill it.
const SHUTDOWN_GRACE: Duration = Duration::from_secs(3);

/// Show the window after this long even if the API has not answered yet, so that a slow cold start
/// looks like a loading app rather than a hang. The frontend retries the API on its own.
const SHOW_WINDOW_AFTER: Duration = Duration::from_secs(10);

/// Stop polling the API after this long. A onefile sidecar unpacks ~100 MB before it listens, which
/// on a cold cache and a slow disk is a lot more than the ten seconds this used to allow.
const READY_TIMEOUT: Duration = Duration::from_secs(60);

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

async fn log_sidecar_output(mut rx: tauri::async_runtime::Receiver<CommandEvent>) {
    while let Some(event) = rx.recv().await {
        match event {
            CommandEvent::Stdout(line) => println!("API: {}", String::from_utf8_lossy(&line)),
            CommandEvent::Stderr(line) => eprintln!("API ERR: {}", String::from_utf8_lossy(&line)),
            _ => {}
        }
    }
}

async fn show_window_when_ready(window: tauri::WebviewWindow) {
    let client = reqwest::Client::new();
    let started = Instant::now();
    let mut shown = false;

    loop {
        let ready = matches!(
            client.get("http://localhost:3001/").send().await,
            Ok(response) if response.status().is_success()
        );
        if ready {
            println!("API ready after {:?}, showing window", started.elapsed());
            // The page may already have loaded and failed to reach the API by now.
            let _ = window.eval("if (typeof loadOverview === 'function') loadOverview();");
            let _ = window.show();
            return;
        }

        let waited = started.elapsed();
        if waited >= READY_TIMEOUT {
            eprintln!("API never became ready; the frontend keeps retrying on its own");
            let _ = window.show();
            return;
        }
        if !shown && waited >= SHOW_WINDOW_AFTER {
            eprintln!("API not ready after {SHOW_WINDOW_AFTER:?}, showing the window anyway");
            let _ = window.show();
            shown = true;
        }

        tokio::time::sleep(Duration::from_millis(200)).await;
    }
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

            match app
                .shell()
                .sidecar("alembic-api")
                .and_then(|command| command.spawn())
            {
                Ok((rx, child)) => {
                    app.manage(SidecarChild(Mutex::new(Some(child))));
                    tauri::async_runtime::spawn(log_sidecar_output(rx));
                    tauri::async_runtime::spawn(show_window_when_ready(window));
                }
                Err(error) => {
                    // There is nothing to wait for. Show the window anyway so the frontend can
                    // report the failure, rather than leaving a dock icon and no window at all.
                    eprintln!("Failed to start the sidecar: {error}");
                    let _ = window.show();
                }
            }

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
