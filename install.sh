#!/bin/bash

SCRIPT_PATH="$(cd -P "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_PATH="${HOME}/.local/share/rhythmbox/plugins/rhythmbox-telegram"
GLIB_SCHEME="org.gnome.rhythmbox.plugins.telegram.gschema.xml"
GLIB_DIR="/usr/share/glib-2.0/schemas"

# Function to uninstall the plugin
function uninstall {
    rm -rf "${PLUGIN_PATH}"
    sudo rm "${GLIB_DIR}/${GLIB_SCHEME}"
    sudo glib-compile-schemas "${GLIB_DIR}/"
    echo "Plugin uninstalled"
    exit 0
}

# Help message
usage() {
    cat <<EOF
Usage:
$0 [OPTION]
-h, --help      show this message.
-u, --uninstall uninstall the plugin
EOF
}


# Parse command-line options
TMP=$(getopt --name=$0 -a --longoptions=help,uninstall -o u,h -- "$@")

if [[ $? != 0 ]]; then
    usage
    exit 1
fi

eval set -- "$TMP"

until [[ $1 == -- ]]; do
    case $1 in
        -h|--help)
            usage
            exit 0
            ;;
        -u|--uninstall)
            uninstall
            ;;
    esac
    shift
done
shift # remove the '--'

# Installation process
install_plugin() {
    # Create plugin directory
    mkdir -p "${PLUGIN_PATH}"

    # Copy plugin files
    cp -r "${SCRIPT_PATH}/"* "${PLUGIN_PATH}"

    # Install Python requirements
    pip3 install -r "${PLUGIN_PATH}/requirements.txt" -t "${PLUGIN_PATH}/lib"

    # Install GLIB schema
    echo "Installing the GLIB schema (password needed)"
    sudo cp "${PLUGIN_PATH}/${GLIB_SCHEME}" "${GLIB_DIR}/"
    sudo glib-compile-schemas "${GLIB_DIR}"

    # Check for TDLib library
    arch=$(uname -m)
    if [[ "$arch" != "x86_64" ]] && [[ -z "$(ldconfig -p | grep tdjson)" ]]; then
        echo "TDLib library is required to run this application." >&2
        echo "Installation instructions are available on GitHub: https://github.com/tdlib/td" >&2
        exit 127
    fi

    echo "Installation completed."
    echo "Please restart Rhythmbox and enable the plugin in the settings."
}

# Execute installation
install_plugin
exit 0
