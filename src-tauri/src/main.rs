#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::net::{SocketAddr, TcpListener, TcpStream};
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::thread;
use std::time::Duration;

use tauri::path::BaseDirectory;
use tauri::{Manager, RunEvent, WebviewUrl, WebviewWindowBuilder};

#[cfg(windows)]
use std::os::windows::process::CommandExt;

fn main() {
    let app = tauri::Builder::default()
        .setup(|app| {
            let listener = TcpListener::bind(("127.0.0.1", 0))?;
            let port = listener.local_addr()?.port();
            drop(listener);

            let server_path = app
                .path()
                .resolve("binaries/clipnest-server.exe", BaseDirectory::Resource)?;
            let mut bundled_path = server_path.parent().unwrap().as_os_str().to_os_string();
            bundled_path.push(";");
            bundled_path.push(std::env::var_os("PATH").unwrap_or_default());
            let mut command = Command::new(server_path);
            command
                .env("CLIPNEST_TAURI", "1")
                .env("CLIPNEST_PORT", port.to_string())
                .env("PATH", bundled_path)
                .stdin(Stdio::null())
                .stdout(Stdio::null())
                .stderr(Stdio::null());
            #[cfg(windows)]
            command.creation_flags(0x0800_0000); // CREATE_NO_WINDOW

            let child = command.spawn()?;
            app.manage(Mutex::new(child));

            let socket = SocketAddr::from(([127, 0, 0, 1], port));
            let mut ready = false;
            for _ in 0..600 {
                if TcpStream::connect_timeout(&socket, Duration::from_millis(100)).is_ok() {
                    ready = true;
                    break;
                }
                if app.state::<Mutex<Child>>().lock().unwrap().try_wait()?.is_some() {
                    break;
                }
                thread::sleep(Duration::from_millis(100));
            }

            let url = if ready {
                WebviewUrl::External(format!("http://127.0.0.1:{port}/").parse()?)
            } else {
                WebviewUrl::App("index.html".into())
            };
            WebviewWindowBuilder::new(app, "main", url)
                .title("Clipnest")
                .inner_size(1280.0, 850.0)
                .min_inner_size(900.0, 620.0)
                .build()?;
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("failed to create Clipnest desktop app");

    app.run(|handle, event| {
        if let RunEvent::Exit = event {
            let state = handle.state::<Mutex<Child>>();
            if let Ok(mut child) = state.lock() {
                #[cfg(windows)]
                {
                    let _ = Command::new("taskkill")
                        .args(["/T", "/F", "/PID", &child.id().to_string()])
                        .creation_flags(0x0800_0000)
                        .stdin(Stdio::null())
                        .stdout(Stdio::null())
                        .stderr(Stdio::null())
                        .status();
                }
                let _ = child.kill();
                let _ = child.wait();
            };
        }
    });
}
