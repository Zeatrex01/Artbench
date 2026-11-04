Artbench {version}
The art side of your game, in one place.

Artbench reads your Unity project, and the art folder you keep beside it if you have one: what each asset is, what
uses it, what nothing uses, and what changed since you last looked. It runs on this computer only.

-- START -------------------------------------------------------------------------------------------------------------

1. Unzip this folder anywhere you like, but not inside a game project (for example Documents\Artbench).
2. Double-click Artbench.bat. Artbench opens in a window of its own (Microsoft Edge or Google Chrome is used to draw
   it; Edge is part of Windows). Closing the window stops Artbench.
   If Windows says it protected your PC, choose "More info", then "Run anyway".
3. In the window: Projects, then "Game project only" (just your Unity project) or "Game project + art folder"
   (your FBX, Blender and texture folder beside the game). Pick the folder; Artbench reads it.

A desktop shortcut: double-click CreateShortcut.bat once.
Artbench writes nothing into your Unity project on its own. Moving a model into the game or back always shows you a
plan first and waits for your OK; a replaced file goes to an _Archive folder, nothing is deleted.

-- OPTIONAL ----------------------------------------------------------------------------------------------------------

Blender 4.2 or newer: model previews, triangle counts and what changed inside a model. Artbench finds Blender by itself.
The Blender add-on (notes pinned to models, kept in the .blend): in Blender, Edit > Preferences > Get Extensions >
  the menu at the top right > Install from Disk, and pick blender_addon\artbench_bridge.zip. Its tab is in the 3D
  view's sidebar (press N).
Your AI tool (Claude Code, Gemini CLI, Codex): Projects > AI connection adds Artbench to Claude Code in one click and
  gives the lines for the others.

-- UPDATING AND REMOVING -------------------------------------------------------------------------------------------

Your settings live in this folder: projects.json and the projects folder (and, for an art folder, inside that folder).
To update, unzip the new version and copy projects.json and the projects folder into it.
To remove Artbench, delete this folder. Nothing else was installed.

Free to use, to change and to share for your own work, with credit ("Artbench by Zeatrex01"). Not for sale: if
someone charged you for Artbench, it was sold against its licence. Licence: LICENSE.txt and NOTICE.txt.
The full guide in Turkish: README_TR.md.


======================================================================================================================

Artbench {version}
Oyununun sanat tarafı, tek yerde.

Artbench Unity projeni ve yanında tuttuğun art klasörünü okur: her varlığın ne olduğunu, neyin kullandığını, neyin
hiç kullanılmadığını ve son baktığından beri ne değiştiğini gösterir. Yalnızca bu bilgisayarda çalışır.

BAŞLARKEN
1. Bu klasörü istediğin yere çıkar, ama bir oyun projesinin içine değil (ör. Belgeler\Artbench).
2. Artbench.bat'a çift tıkla. Artbench kendi penceresinde açılır (çizmek için Microsoft Edge ya da Google Chrome
   kullanılır; Edge Windows'la gelir). Pencereyi kapatınca Artbench de kapanır.
   Windows "bilgisayarınızı korudu" derse "Ek bilgi", sonra "Yine de çalıştır".
3. Pencerede: Projeler, sonra "Yalnızca oyun projesi" ya da "Oyun projesi + art klasörü". Klasörü seç, Artbench okur.

Masaüstü kısayolu için CreateShortcut.bat'a bir kez çift tıkla. Artbench Unity projene kendiliğinden hiçbir şey
yazmaz; bir modeli oyuna gönderme ya da geri alma her zaman önce plan gösterir ve onayını bekler.

İSTEĞE BAĞLI
Blender 4.2+: model önizlemeleri, üçgen sayıları, modelin içinde ne değiştiği.
Blender eklentisi (modelin üstüne iğnelenen, .blend içinde saklanan notlar): Blender'da Edit > Preferences >
  Get Extensions > sağ üstteki menü > Install from Disk, blender_addon\artbench_bridge.zip.
Yapay zekâ aracın: Projeler > AI connection.

GÜNCELLEME VE KALDIRMA
Ayarların bu klasördedir: projects.json ve projects klasörü. Güncellerken yeni sürümü çıkar, bu ikisini içine kopyala.
Kaldırmak için bu klasörü sil; başka hiçbir şey kurulmadı.

Kendi işin için kullanmak, değiştirmek ve paylaşmak ücretsizdir; atıf yapman yeter ("Artbench by Zeatrex01").
Satılamaz: Artbench için senden ücret alındıysa lisansına aykırı satılmıştır. Lisans: LICENSE.txt ve NOTICE.txt.
Ayrıntılı kılavuz: README_TR.md.
