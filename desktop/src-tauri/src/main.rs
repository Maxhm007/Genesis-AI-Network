use tauri_plugin_shell::{process::CommandEvent, ShellExt};

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_opener::init())
        .setup(|app| {
            let app_handle = app.handle().clone();
            let command = app.shell().sidecar("genesis-core")?;
            let (mut rx, _child) = command.spawn()?;
            tauri::async_runtime::spawn(async move {
                while let Some(event) = rx.recv().await {
                    match event {
                        CommandEvent::Stdout(bytes) => {
                            println!("GENESIS_CORE: {}", String::from_utf8_lossy(&bytes));
                        }
                        CommandEvent::Stderr(bytes) => {
                            eprintln!("GENESIS_CORE: {}", String::from_utf8_lossy(&bytes));
                        }
                        _ => {}
                    }
                }
                let _ = app_handle;
            });
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running Genesis AI Desktop");
}
