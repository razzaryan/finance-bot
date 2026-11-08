; Skrip Inno Setup untuk aplikasi Keuangan.
;
; Build dari root repo:
;   powershell -ExecutionPolicy Bypass -File packaging\build_installer.ps1
;
; Hasil: dist\installer\Keuangan-Setup-1.0.0.exe
;
; Keputusan penting:
; - Dipasang per-user (tanpa UAC) ke %LOCALAPPDATA%\Programs\Keuangan.
;   Data pengguna tetap di %APPDATA%\Keuangan, jadi update/timpa aplikasi tidak
;   pernah menyentuh database.
; - Pilihan "hapus data" disimpan ke registry saat instalasi, karena uninstaller
;   berjalan sebagai proses terpisah dan tidak melewati InitializeWizard.
;   Tanpa ini, uninstaller akan crash saat membaca halaman wizard yang tidak ada.

#define MyAppName "Keuangan"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "Keuangan"
#define MyAppExeName "Keuangan.exe"
#define SourceDir "..\dist\Keuangan"

[Setup]
AppId={{8C2F1B57-6E4D-4B2C-9A31-5D7E8F0A1C44}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
VersionInfoVersion={#MyAppVersion}
VersionInfoDescription=Aplikasi pencatatan keuangan pribadi
DefaultDirName={localappdata}\Programs\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist\installer
OutputBaseFilename=Keuangan-Setup-{#MyAppVersion}
SetupIconFile=keuangan.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
CloseApplications=yes
RestartApplications=no
AllowNoIcons=yes
DisableWelcomePage=no

[Languages]
Name: "id"; MessagesFile: "Indonesian.isl"
Name: "en"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Buat ikon di Desktop"; GroupDescription: "Ikon tambahan:"; Flags: checkedonce
Name: "startmenu"; Description: "Buat ikon di Start Menu"; GroupDescription: "Ikon tambahan:"; Flags: checkedonce

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "PANDUAN.txt"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: startmenu
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon
Name: "{autoprograms}\Panduan {#MyAppName}"; Filename: "{app}\PANDUAN.txt"; Tasks: startmenu

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Jalankan {#MyAppName} sekarang"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}"

[Code]
const
  DataKey = 'Software\Keuangan';
  DataValue = 'DeleteDataOnUninstall';

var
  RemoveDataPage: TInputOptionWizardPage;

procedure InitializeWizard;
begin
  RemoveDataPage := CreateInputOptionPage(wpSelectTasks,
    'Data pribadi kamu',
    'Database keuangan tidak dihapus otomatis.',
    'Aplikasi menyimpan data di folder profil Windows kamu. Pilih tindakan saat aplikasi dicopot nanti.',
    False, False);
  RemoveDataPage.Add('Biarkan data saya (disarankan)');
  RemoveDataPage.Add('Hapus juga data saat aplikasi dicopot');
  RemoveDataPage.Values[0] := True;
end;

function DataDir(): String;
begin
  Result := ExpandConstant('{userappdata}\Keuangan');
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  DeleteData: Cardinal;
begin
  if CurStep = ssPostInstall then
  begin
    if RemoveDataPage.Values[1] then
      DeleteData := 1
    else
      DeleteData := 0;
    RegWriteDWordValue(HKCU, DataKey, DataValue, DeleteData);
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DeleteData: Cardinal;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    if RegQueryDWordValue(HKCU, DataKey, DataValue, DeleteData) then
    begin
      if DeleteData = 1 then
        DelTree(DataDir(), True, True, True);
    end;
    RegDeleteKeyIfEmpty(HKCU, DataKey);
  end;
end;
