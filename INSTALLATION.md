# Installation

This guide is written for the Windows operating system. Linux users will need to install manually.

Ensure that Dragonfly 2024.1 is installed. Close all Dragonfly windows.

> 💡 **Note:** If you are installing the plugin with a  version of Dragonfly different from 2024.1: (1) the plugin is not guaranteed to work correctly; (2) the plugin must be installed manually or the `DRAGONFLY_INSTALL_PATH` variable must be updated accordingly in the installation script.

## Downloading the Latest Release

Head to the [releases page](https://github.com/AlexanderJCS/dsb-plugin/releases/) and find the latest release. Click **Source Code (zip)** to download the source code.

## Installing the Plugin

Extract the zip file containing the source code and open it. Find the `install.bat` file and run it.

> ⚠️ **Warning:** Installing DSB requires the Dragonfly installation to be modified. While unlikely, this may cause instability with the base Dragonfly application. If you want to be cautious, you can backup the `C:\Program Files\Dragonfly\Python_env` folder. Otherwise, any broken behavior will require a reinstallation of Dragonfly.

> ℹ️ **Info:** Windows may give a warning that the installer script is an unrecognized app. This is because the script is not digitally signed and widely distributed. Simply click **More info → Run Anyway**.

> ℹ️ **Info:** The installer script will ask for administrator privileges. This is required to modify Dragonfly files and install the program.

## Verification

Open Dragonfly. On the application toolbar (top of the screen), you should see a new **Plugins** tab. Select **Plugins → Start DSB**. A new window should appear, indicating that the plugin was installed successfully.

> 🔧 **Troubleshooting:** If the **Plugins → Start DSB** button is not available, the most likely culprit is that the files were not copied properly. Check that you see a folder starting with **DSB** at `C:\ProgramData\ORS\Dragonfly2024.1\pythonAllUsersExtensions\Plugins`. Try re-running the installation script, and if that does not work, install the plugin manually.

> 🔧 **Troubleshooting:** If the **Plugins → Start DSB** fails to launch a plugin window, DSB's dependencies are likely not installed properly. Try re-running the installation script and check for errors in the console relating to package installation (warnings are fine).