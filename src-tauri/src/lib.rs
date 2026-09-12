use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};
use tauri::{Manager, RunEvent};
use tauri_plugin_shell::process::{CommandChild, CommandEvent};
use tauri_plugin_shell::ShellExt;

/// Where the sidecar listens. Spelled as an address rather than `localhost`, which Windows resolves
/// to ::1 first: that costs a refused connection on every request if the sidecar only managed to
/// bind the v4 loopback.
const API_BASE: &str = "http://127.0.0.1:3001";

struct SidecarChild {
    child: Mutex<Option<CommandChild>>,
    /// Set once the shell plugin reports the process gone. Windows offers no cheap liveness check to
    /// fall back on, so this is what tells us the sidecar has really finished.
    exited: Arc<AtomicBool>,
}

/// How long the sidecar gets to exit on its own after being asked politely. The PyInstaller
/// bootloader deletes its ~280 MB extraction directory on the way out, which is the slow part.
const SHUTDOWN_GRACE: Duration = Duration::from_secs(10);

/// How long it gets after being signalled, before the handle is taken down the hard way.
const KILL_GRACE: Duration = Duration::from_secs(3);

/// Show the window after this long even if the API has not answered yet, so that a slow cold start
/// looks like a loading app rather than a hang. The frontend retries the API on its own.
const SHOW_WINDOW_AFTER: Duration = Duration::from_secs(10);

/// Stop polling the API after this long. A onefile sidecar unpacks ~280 MB before it listens, which
/// on a cold cache, a slow disk, or with a virus scanner reading every extracted file takes a lot
/// longer than it sounds. The frontend gives up at the same five minutes.
const READY_TIMEOUT: Duration = Duration::from_secs(300);

/// A client for the local API.
///
/// `no_proxy`, because a machine with HTTP_PROXY or ALL_PROXY set (and no matching no_proxy entry)
/// would otherwise have reqwest send a request for 127.0.0.1 through the proxy, where it fails -
/// leaving the health check below stuck on an API that is in fact up.
fn local_client() -> reqwest::Client {
    reqwest::Client::builder()
        .no_proxy()
        .build()
        .unwrap_or_else(|_| reqwest::Client::new())
}

/// Ask the server to exit through its own shutdown route.
///
/// This is the polite path, and the one that keeps the user's temp folder from filling up: the
/// sidecar is a PyInstaller onefile bundle, so the process we spawned is the bootloader and the
/// server runs in a child of it. The bootloader deletes its ~280 MB extraction directory only when
/// that child exits by itself. Kill either process and the directory stays behind - once per launch.
fn request_http_shutdown() -> bool {
    tauri::async_runtime::block_on(async {
        matches!(
            local_client()
                .post(format!("{API_BASE}/shutdown"))
                .timeout(Duration::from_secs(2))
                .send()
                .await,
            Ok(response) if response.status().is_success()
        )
    })
}

/// Signal the sidecar to stop, for when the shutdown route could not be reached.
#[cfg(unix)]
fn request_shutdown(pid: u32) {
    // SIGTERM reaches the bootloader, which takes its child down and still cleans up after itself.
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
    // Windows has no SIGTERM, and a bare kill would leave the Python child the bootloader spawned
    // holding port 3001. `taskkill /T` takes the tree down together. This skips the bootloader's
    // cleanup, which is why it is the fallback and not the first thing tried.
    use std::os::windows::process::CommandExt;
    const CREATE_NO_WINDOW: u32 = 0x0800_0000;
    match std::process::Command::new("taskkill")
        .args(["/PID", &pid.to_string(), "/T", "/F"])
        .creation_flags(CREATE_NO_WINDOW)
        .status()
    {
        Ok(status) if status.success() => {}
        Ok(status) => eprintln!("taskkill on the sidecar returned {status}"),
        Err(error) => eprintln!("Could not run taskkill on the sidecar: {error}"),
    }
}

#[cfg(windows)]
fn is_running(_pid: u32) -> bool {
    // Nothing cheap to ask here without pulling in the Windows API: treat the process as alive and
    // let the exit event that the shell plugin delivers be the authority.
    true
}

/// Whether the sidecar is gone, waiting up to `grace` for it.
fn wait_for_exit(pid: u32, exited: &AtomicBool, grace: Duration) -> bool {
    let deadline = Instant::now() + grace;
    loop {
        if exited.load(Ordering::SeqCst) || !is_running(pid) {
            return true;
        }
        if Instant::now() >= deadline {
            return false;
        }
        std::thread::sleep(Duration::from_millis(50));
    }
}

async fn log_sidecar_output(
    mut rx: tauri::async_runtime::Receiver<CommandEvent>,
    exited: Arc<AtomicBool>,
) {
    while let Some(event) = rx.recv().await {
        match event {
            CommandEvent::Stdout(line) => println!("API: {}", String::from_utf8_lossy(&line)),
            CommandEvent::Stderr(line) => eprintln!("API ERR: {}", String::from_utf8_lossy(&line)),
            CommandEvent::Terminated(payload) => {
                println!("API exited with code {:?}", payload.code);
                exited.store(true, Ordering::SeqCst);
            }
            _ => {}
        }
    }
    // The plugin drops its end of the channel once the process is gone and both pipes are drained,
    // so reaching here means the same thing as the event above.
    exited.store(true, Ordering::SeqCst);
}

async fn show_window_when_ready(window: tauri::WebviewWindow) {
    let client = local_client();
    let started = Instant::now();
    let mut shown = false;

    loop {
        let ready = matches!(
            client.get(format!("{API_BASE}/")).send().await,
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
    let Ok(mut guard) = state.child.lock() else {
        return;
    };
    let Some(child) = guard.take() else {
        return;
    };

    let pid = child.pid();
    let exited = &state.exited;

    // Asked to stop, it exits by itself and the bootloader gets to clean up behind it.
    if request_http_shutdown() && wait_for_exit(pid, exited, SHUTDOWN_GRACE) {
        println!("Sidecar exited cleanly");
        return;
    }

    // The route was unreachable (a sidecar still unpacking has not opened its port yet) or the
    // process outlasted the grace period.
    request_shutdown(pid);
    if wait_for_exit(pid, exited, KILL_GRACE) {
        println!("Sidecar exited after being signalled");
        return;
    }

    eprintln!("Sidecar did not exit within {KILL_GRACE:?}, forcing it");
    let _ = child.kill();
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let mut builder = tauri::Builder::default();

    // Before every other plugin: a second launch hands its arguments to the instance that is
    // already running and exits here, which has to happen before this one spawns a sidecar of its
    // own. Without it, the second window ends up served by the first window's sidecar - its own
    // steps aside, seeing the port taken - and then loses its API the moment the first window is
    // closed and shuts that sidecar down.
    #[cfg(desktop)]
    {
        builder = builder.plugin(tauri_plugin_single_instance::init(|app, _args, _cwd| {
            if let Some(window) = app.get_webview_window("main") {
                let _ = window.show();
                let _ = window.unminimize();
                let _ = window.set_focus();
            }
        }));
    }

    let app = builder
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
                    let exited = Arc::new(AtomicBool::new(false));
                    app.manage(SidecarChild {
                        child: Mutex::new(Some(child)),
                        exited: exited.clone(),
                    });
                    tauri::async_runtime::spawn(log_sidecar_output(rx, exited));
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
