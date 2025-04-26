# ControlHub Client

**[Read this page in Russian / Читать на русском](README.ru.md)**

ControlHub Client is an agent application that allows remote code execution on managed computers. It connects to the ControlHub platform, receives execution tasks, runs Python code, and reports execution results back to the platform.

## Installation

Install the client using the latest installer from the [Releases](https://github.com/control-hub/client/releases) page:

1. Download the latest `ControlHub_Setup.exe` file
2. Run the installer
3. Enter your token when prompted
4. Follow the installation instructions

The installer will:
- Set up required dependencies
- Configure the client to start automatically with Windows

## Features

- Automatic system registration with the ControlHub platform
- Secure token-based authentication
- Real-time task execution monitoring
- System status reporting (online, idle, running)
- Automatic MAC and IP address detection
- Concurrent execution management
- Cleanup of temporary files after execution

## Usage

After installation, the client runs in the background and automatically:

1. Connects to the ControlHub server
2. Updates its status and network information
3. Subscribes to execution tasks for this computer
4. Executes Python code as tasks arrive
5. Reports execution results back to the platform

No manual intervention is required after installation.

## Troubleshooting

If you encounter any issues:

1. Check your internet connection
2. Verify your token is valid
3. Restart the client service
4. Check the logs in the application directory

## License

This project is licensed under the MIT License - see the LICENSE file for details.