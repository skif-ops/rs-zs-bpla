# PyInstaller spec: builds muhoed-pki.exe (server administration) from server/pki.
# Run from the `server` directory: pyinstaller pki/pyinstaller_muhoed_pki.spec
import os
block_cipher = None
a = Analysis(['__main__.py'], pathex=[os.path.abspath(os.path.join(SPECPATH, '..'))], binaries=[], datas=[],
             hiddenimports=['cryptography.hazmat.backends.openssl'], hookspath=[], runtime_hooks=[],
             excludes=['tkinter', 'numpy', 'scipy', 'pandas', 'matplotlib'], cipher=block_cipher, noarchive=False)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(pyz, a.scripts, a.binaries, a.zipfiles, a.datas, [], name='muhoed-pki', debug=False,
          bootloader_ignore_signals=False, strip=False, upx=False, console=True)
