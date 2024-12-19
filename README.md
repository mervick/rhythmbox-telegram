# Rhythmbox Telegram Music Plugin

Rhythmbox-Telegram is a plugin for Rhythmbox that allows you to listen to and download music from Telegram directly within Rhythmbox.

![Telegram playlist in Rhythmbox](screenshots/playlist.png)
[**More screenshots here**](screenshots)

## Key Features

- **Telegram Integration**: Easily add Telegram channels and chats to Rhythmbox as playlists, simplifying your music browsing experience.

- **Browse Audio Files**: Easily browse, search, and organize audio files shared in Telegram directly from Rhythmbox, ensuring quick and convenient access to your favorite tracks.

- **Listen to Music**: Enjoy audio content from Telegram directly in Rhythmbox, allowing continuous music playback without switching between applications.

- **Download to Library**: Download audio files from Telegram directly to your Rhythmbox library, expanding your music collection with the content you enjoy.

With Rhythmbox-Telegram, enjoy the convenience of accessing and loading your favorite Telegram audio content into your music library, transforming how you organize and enjoy your music collection.


## Installation

**Note:** Regardless of the installation method, the plugin depends on TDLib. For architectures other than x64, TDLib must be installed manually.  Refer to the official [TDLib GitHub repository](https://github.com/tdlib/td) for instructions.

### Method 1: Install from Debian Package

For Debian-like systems with 64-bit architecture, download the latest `.deb` package from the [releases page](https://github.com/mervick/rhythmbox-telegram/releases). Then install it using the following command:

```sh
sudo dpkg -i rhythmbox-telegram-plugin_*.deb
```

**Note:** For other architectures, you can still use the Debian package, but you will need to [install TDLib manually](https://github.com/tdlib/td).

---

### Method 2: Install Using the Installation Script

Run the `install.sh` script from the repository:

```sh
git clone https://github.com/mervick/rhythmbox-telegram
bash rhythmbox-telegram/install.sh
   ```

The script will handle the entire installation process, including downloading dependencies, setting up the plugin, and compiling schemas.

**Note:** If the architecture is different from x64, you will need to [install TDLib manually](https://github.com/tdlib/td).

---

### Method 3: Manual Installation

Download the plugin from the repository, install required pip3 libs, copy plugin files to the Rhythmbox plugins folder, then compile GLib schemas:

```sh
# clone plugin gi
git clone https://github.com/mervick/rhythmbox-telegram
# install required python libs
pip3 install -r "rhythmbox-telegram/requirements.txt" -t "rhythmbox-telegram/lib"
# create plugin dir
mkdir -p ~/.local/share/rhythmbox/plugins/rhythmbox-telegram/
# copy plugin files
cp -r rhythmbox-telegram/* ~/.local/share/rhythmbox/plugins/rhythmbox-telegram
# copy plugin glib schema
sudo cp rhythmbox-telegram/org.gnome.rhythmbox.plugins.telegram.gschema.xml /usr/share/glib-2.0/schemas/
# update glib schema
sudo glib-compile-schemas /usr/share/glib-2.0/schemas/
```

**Note:** As in all cases, if the architecture is different from x64, you will need to [install TDLib manually](https://github.com/tdlib/td).

### Restart Rhythmbox

After installing the plugin, if Rhythmbox is open, restart it.

## Activation

After installing the plugin, you need to:
- Activate it in the Rhythmbox settings 
- Obtain a Telegram API ID 
- Authenticate the Telegram user

### Obtaining Telegram API ID

In order to obtain an API id you need to do the following:

- Log in to your Telegram core: https://my.telegram.org.
- Go to [API development tools](https://my.telegram.org/apps) and fill out the form.
- You will get `api_id` and `api_hash` parameters required for user authorization.

More detailed instructions can be found in the [Telegram documentation](https://core.telegram.org/api/obtaining_api_id)

### Authorization

After obtaining the API ID, in the plugin settings, input the received `api_id` and `api_hash`, along with your Telegram user's phone number. Then, press the 'Connect' button. Telegram will send you a code for authorization to any connected Telegram app.

### Adding your music to Rhythmbox

After successfully connecting Telegram to Rhythmbox, in the plugin settings, you'll be able to add Telegram channels, groups and chats to listen to your favorite music.

**Note:** Sometimes, after adding or removing channels and groups, it is necessary to restart Rhythmbox.

## Telegram API Usage and Operations

The plugin uses the Telegram API strictly for reading purposes. **No write operations are performed**.  

The following actions are carried out:

* Authorization process
* Retrieving the contact list (necessary to fetch groups and channels)
* Iterating over all messages in groups and channels selected as "Music Sources" in the plugin settings (only audio files are searched; messages and audio messages are ignored)
* Downloading of audio files
* Getting a public link to a message with an audio file

No other operations are conducted.

### TDLib API Methods and Handlers Used

The plugin uses only the following methods and handlers:

* `setTdlibParameters`
* `checkDatabaseEncryptionKey`
* `getAuthorizationState`
* `setAuthenticationPhoneNumber`
* `checkAuthenticationPassword`
* `checkAuthenticationCode`
* `loadChats`
* `getChats`
* `getChat`
* `getMessage`
* `getChatHistory`
* `downloadFile`
* `getMessageLink`
* `updateAuthorizationState`
* `updateNewChat`

### Caching and Audio File Retrieval

The plugin caches information about retrieved audio files. The audio file list is initially fetched in small batches to stay within API quota limits. If the initial retrieval is incomplete, remaining tracks will be loaded later. The plugin automatically fetches new files and continues to load any remaining tracks with intervals of 5-10 minutes, both during initialization and while retrieving new content. This approach ensures efficient, quota-compliant, and timely updates of new content.

## Data Encryption and Storage

We strive to protect your data by implementing various security measures:

### Authentication Data

Authentication data is encrypted and stored within the GNOME Keyring. This ensures that sensitive information is securely protected within the GNOME environment, providing an additional layer of security against unauthorized access.

### Data from Telegram

Data obtained from Telegram is encrypted using a user-provided encryption key and managed by the official Telegram client, [TDLib](https://core.telegram.org/tdlib).  
The encrypted databases are stored at: `~/.local/share/rhythmbox/telegram/*/database`

### Temporary Audio Files

Temporary audio files are stored at `~/.local/share/rhythmbox/telegram/*/files/music`  
You can delete these files at any time. However, please note that deleting these files manually will not remove their entries from the database. For safe removal, you can delete audio files through the plugin settings, ensuring the database integrity is maintained.

### Additional Data Storage

**Audio Metadata:** We store metadata of audio files in an unencrypted format. This includes data obtained from Telegram, such as the chat identifier, message identifier within the chat, publication date and time, file size, file name, audio tags and the file's location in the file system.

**Chat Information:** We store information about your chats, including chat names and identifiers, in an encrypted format to ensure privacy and security.

This data is stored within the database at: `~/.local/share/rhythmbox/telegram/*/data.sqlite`


## License

[Rhythmbox-Telegram](https://github.com/mervick/rhythmbox-telegram) is an open-source plugin distributed under the [GPL-3 license](https://github.com/mervick/rhythmbox-telegram/blob/master/LICENCE), ensuring that it remains freely accessible to all users and encouraging community collaboration and contribution.


## Contribute

If you like our plugin you can support the ongoing development and maintenance of Rhythmbox-Telegram by spreading the word about the plugin or making contributions via PayPal or cryptocurrency donations, ensuring its continued improvement and availability for the community.

