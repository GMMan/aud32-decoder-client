Sonix Audio32 Decoder Client
============================

This program converts Sonix Audio32 files using the Audio32 codec
(based on G.722.1) to WAV.

Setup
-----
Create a virtualenv and install the dependencies in `requirements.txt`. Then
set up the host side by building the [host code](https://github.com/GMMan/aud32-decoder-host)
and patching the SNC7320 core 1 ROM image.

There are some constants `Converter` that need to match the host side. In
particular, if you've modified the host code, you may need to update `BP_ADDR`
to the address of the `bp` function in host code.

Before running the program, start up QEMU with the patched ROM image.

Usage
-----

```
main.py <src_path> <dest_path>
```

- `src_path`: The path to the folder containing the files you want to convert.
  please make sure the directory does not contain any subdirectories, only
  files, as the program doesn't handle recursive files.
- `dest_path`: The path to the folder to save the converted `.wav` files to.
  This path should already exist.
