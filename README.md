# Rhythmbox Telegram Music Plugin

Rhythmbox-Telegram is a plugin for Rhythmbox that allows you to listen to and download music from Telegram directly within Rhythmbox.

![Telegram playlist in Rhythmbox](screenshots/playlist.png)
[**More screenshots here**](screenshots)

## Key Features

- **Telegram Integration**: Easily add Telegram channels and chats to Rhythmbox as playlists, consolidating your digital communication and music browsing in one convenient interface.

- **Browse Audio Files**: Effortlessly browse through audio files shared in Telegram directly from within Rhythmbox, ensuring quick access to your desired tracks.

- **Listen to Music**: Seamlessly stream audio content from Telegram through Rhythmbox, enabling uninterrupted music playback without the need to switch between applications.

- **Download to Library**: Download audio files from Telegram directly to your Rhythmbox library, expanding your music collection with the content you enjoy.

With Rhythmbox-Telegram, enjoy the convenience of accessing your favorite Telegram audio content alongside your music library, revolutionizing the way you interact with both your digital communication platforms and your music collection.


## Installation

To enable plugin, you need first install  `python-telegram` - Telegram library for python backed by the official Telegram client - [TDLib](https://core.telegram.org/tdlib)

```sh
pip3 install python-telegram==0.18.0
```

Next, if Rhythmbox player is open, please close it, then proceed to download the plugin from the repository and move it to the Rhythmbox plugins folder, and compile glib schemas

```sh
git clone https://github.com/mervick/rhythmbox-telegram ~/.local/share/rhythmbox/plugins/rhythmbox-telegram
glib-compile-schemas ~/.local/share/rhythmbox/plugins/rhythmbox-telegram
```


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

After successfully connecting Telegram to Rhythmbox, in the plugin settings, you'll be able to add Telegram channels and chats to listen to your favorite music.

### Enjoy the tunes!

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

