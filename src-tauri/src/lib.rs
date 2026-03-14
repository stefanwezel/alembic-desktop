use std::sync::Mutex;
use tauri::Manager;
use tauri_plugin_shell::process::{CommandChild, CommandEvent};
use tauri_plugin_shell::ShellExt;

struct SidecarChild(Mutex<Option<CommandChild>>);

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
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
            let (mut rx, child) = sidecar_command
                .spawn()
                .expect("failed to spawn sidecar");

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
                } else {
                    eprintln!("API failed to become ready within 10s, showing window anyway");
                }
                let _ = window_clone.show();
            });

            Ok(())
        })
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::Destroyed = event {
                if let Some(state) = window.try_state::<SidecarChild>() {
                    if let Ok(mut guard) = state.0.lock() {
                        if let Some(child) = guard.take() {
                            let _ = child.kill();
                            println!("Sidecar process killed");
                        }
                    }
                }
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
