#!/usr/bin/env bash

# install schema
#sudo cp ./org.gnome.rhythmbox.plugins.telegram.gschema.xml /usr/share/glib-2.0/schemas/
#sudo glib-compile-schemas /usr/share/glib-2.0/schemas/

glib-compile-schemas ./
pip3 install -r requirements.txt
mkdir -p ~/.local/share/rhythmbox/plugins/
#rm -rf ~/.local/share/rhythmbox/plugins/rhythmbox-telegram/
cp -r ./ ~/.local/share/rhythmbox/plugins/rhythmbox-telegram/
