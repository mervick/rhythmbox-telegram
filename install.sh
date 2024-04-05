#!/bin/bash

SCRIPT_NAME=`basename "$0"`
SCRIPT_PATH=${0%`basename "$0"`}
PLUGIN_PATH="${HOME}/.local/share/rhythmbox/plugins/rhythmbox-telegram"
GLIB_SCHEME="org.gnome.rhythmbox.plugins.rhythmbox-telegram.gschema.xml"
SCHEMA_FOLDER="schema/"
GLIB_DIR="/usr/share/glib-2.0/schemas/"


function uninstall {
    rm -rf "${PLUGIN_PATH}"
    sudo rm "${GLIB_DIR}${GLIB_SCHEME}"
    sudo glib-compile-schemas "${GLIB_DIR}"
    echo "plugin uninstalled"
    exit
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
    shift # move the arg list to the next option or '--'
done
shift # remove the '--', now $1 positioned at first argument if any


########################## START INSTALLATION ################################

#build the dirs
mkdir -p $PLUGIN_PATH

#copy the files
cp -r "${SCRIPT_PATH}"* "$PLUGIN_PATH"

# install requirements
pip3 install -r "$PLUGIN_PATH"/requirements.txt

#remove the install script from the dir (not needed)
#rm "${PLUGIN_PATH}${SCRIPT_NAME}"

#install the glib schema
echo "Installing the glib schema (password needed)"
sudo cp "${PLUGIN_PATH}${SCHEMA_FOLDER}${GLIB_SCHEME}" "$GLIB_DIR"
sudo glib-compile-schemas "$GLIB_DIR"

#exit