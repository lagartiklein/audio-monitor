; Script de instalación para FichatechMonitor
[Setup]
AppName=FichatechMonitor
AppVersion=1.0
DefaultDirName={pf}\FichatechMonitor
DefaultGroupName=FichatechMonitor
OutputDir=release
OutputBaseFilename=FichatechMonitor-Setup
Compression=lzma
SolidCompression=yes

[Files]
Source: "release\FichatechMonitor.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\FichatechMonitor"; Filename: "{app}\FichatechMonitor.exe"
Name: "{userdesktop}\FichatechMonitor"; Filename: "{app}\FichatechMonitor.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Crear icono en el escritorio"; GroupDescription: "Opciones adicionales:"

[Run]
Filename: "{app}\FichatechMonitor.exe"; Description: "Ejecutar FichatechMonitor"; Flags: postinstall nowait skipifsilent
