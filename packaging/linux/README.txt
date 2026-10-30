Dogear for Linux

Dogear turns books into audiobooks and talking books you can navigate by chapter,
heading, and page. Everything it needs is in this folder, including its voice, so it
works without an internet connection.

To install:
1. Open a terminal in this folder.
2. Run: sh install.sh
   No administrator password is needed. Dogear is installed for you alone.

To start Dogear, choose Dogear in your applications menu. A terminal window opens and
shows a link for your web browser. Keep that window open while you use Dogear; close it,
or press Ctrl+C in it, to stop Dogear.

From a terminal, the dogear command works too. Run: dogear --help

To remove Dogear, run: sh ~/.local/opt/dogear/uninstall.sh

Dogear needs a 64-bit PC (x86_64) with glibc 2.28 or newer, which includes Ubuntu
20.04, Debian 10, Fedora 29, and RHEL 8 or newer.

Dogear is free software under the Apache License 2.0 (dogear/LICENSE.txt). The other
software it includes, and where to get its source code, is listed in
dogear/THIRD-PARTY-NOTICES.txt.
