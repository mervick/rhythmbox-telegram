#!/bin/bash

SCRIPT_PATH="$(cd -P "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_PATH="${HOME}/.local/share/rhythmbox/plugins/rhythmbox-telegram"
GLIB_SCHEME="org.gnome.rhythmbox.plugins.telegram.gschema.xml"
GLIB_DIR="/usr/share/glib-2.0/schemas"


function uninstall {
    rm -rf "${PLUGIN_PATH}"
    sudo rm "${GLIB_DIR}/${GLIB_SCHEME}"
    sudo glib-compile-schemas "${GLIB_DIR}/"
    echo "Plugin uninstalled"
    exit 0
}


################################ USAGE #######################################

usage=$(
cat <<EOF
Usage:
$0 [OPTION]
-h, --help      show this message.
-u, --uninstall uninstall the plugin

EOF
)

########################### OPTIONS PARSING #################################

#parse options
TMP=`getopt --name=$0 -a --longoptions=help,uninstall -o u,h -- $@`

if [[ $? == 1 ]]
then
    echo
    echo "$usage"
    exit
fi

eval set -- $TMP

until [[ $1 == -- ]]; do
    case $1 in
        -h|--help)
            echo "$usage"
            exit
            ;;
        -u|--uninstall)
            uninstall
            exit
            ;;
    esac
    shift
done
shift # remove the '--', now $1 positioned at first argument if any


########################## INSTALLATION ################################

# build the dirs
mkdir -p "${PLUGIN_PATH}"

# copy the files
cp -r "${SCRIPT_PATH}/"* "$PLUGIN_PATH"

# install requirements
pip3 install -r "$PLUGIN_PATH/requirements.txt" -t "$PLUGIN_PATH/lib"

# install the glib schema
echo "Installing the glib schema (password needed)"
sudo cp "${PLUGIN_PATH}/${GLIB_SCHEME}" "$GLIB_DIR/"
sudo glib-compile-schemas "$GLIB_DIR/"

arch=$(uname -m)

case "$arch" in
    x86_64) ;;
    *)
      if [[ "$(ldconfig -p | grep tdjson)" == "" ]]; then
        echo "TDLib library is required to run this application." >&2
        echo "Installation instructions are available on GitHub: https://github.com/tdlib/td" >&2
        exit 127
      fi
    ;;
esac

echo "Installation completed."
echo "Please restart Rhythmbox and enable the plugin in the settings."

exit 0
