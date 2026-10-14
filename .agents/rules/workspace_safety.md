# Workspace & Directory Safety Rules

## Strict Scope Guardrails
1. **Workspace Boundary**:
   - Seluruh pekerjaan, repositori sementara, file scratch, dan eksperimen HANYA boleh berada di dalam workspace aktif saat ini (`d:\Coding\token-harbor-auto`).
   - DILARANG membuat cloning git baru, folder pengujian, atau file apapun di `D:\Coding` di luar workspace aktif.

2. **Larangan Modifikasi Direktori Luar**:
   - DILARANG menghapus, mengganti nama, memindahkan, atau mengedit file/folder apapun di direktori `D:\Coding` di luar workspace aktif tanpa izin tertulis eksplisit dari pengguna.
   - Bila pengguna menyebutkan folder lain, konfirmasi terlebih dahulu sebelum melakukan aksi manipulasi file.

3. **Temporary & Scratch Files**:
   - Semua file log harus masuk ke folder `logs/`.
   - File sementara agen harus diletakkan di artifact scratch directory, bukan di folder root user.
