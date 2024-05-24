# Rhythmbox Telegram Music Plugin

Rhythmbox-Telegram is a Rhythmbox plugin that allows you to listen to and download music directly from your favorite music player, Rhythmbox.

## Key Features

- **Telegram Integration**: Easily add Telegram channels and chats to Rhythmbox as playlists, consolidating your digital communication and music browsing in one convenient interface.

- **Browse Audio Files**: Effortlessly browse through audio files shared in Telegram directly from within Rhythmbox, ensuring quick access to your desired tracks.

- **Listen to Music**: Seamlessly stream audio content from Telegram through Rhythmbox, enabling uninterrupted music playback without the need to switch between applications.

- **Download to Library**: Download audio files from Telegram directly to your Rhythmbox library, expanding your music collection with the content you enjoy.

With Rhythmbox-Telegram, enjoy the convenience of accessing your favorite Telegram audio content alongside your music library, revolutionizing the way you interact with both your digital communication platforms and your music collection.


## Installation

To enable plugin, you need first install  `python-telegram` - unofficial Telegram API library for python backed by the official Telegram library - [TDLib](https://core.telegram.org/tdlib)

```sh
pip3 install python-telegram==0.18.0
```

Next, if Rhythmbox player is open, please close it, then proceed to download the plugin from the repository and move it to the Rhythmbox plugins folder

```sh
git clone https://github.com/mervick/rhythmbox-telegram ~/.local/share/rhythmbox/plugins/rhythmbox-telegram
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
- You will get basic addresses as well as the `api_id` and `api_hash` parameters required for user authorization.

More detailed instructions can be found in the [Telegram documentation](https://core.telegram.org/api/obtaining_api_id)

### Authorization

After obtaining the API ID, in the plugin settings, input the received `api_id` and `api_hash`, along with your Telegram user's phone number. Then, press the 'Connect' button. Telegram will send you a code for authorization to any connected Telegram app.

### Adding your music to Rhythmbox

After successfully connecting Telegram to Rhythmbox, in the plugin settings, you'll be able to add Telegram channels and chats to listen to your favorite music.


## Secure

We strive to protect your data by implementing various security measures.

- All your authentication data, is **encrypted** and stored within GNOME Keyring. This ensures that sensitive information is securely protected within the GNOME environment.
- All your data obtained from Telegram (except audio files and their metadata) is **encrypted** using a user-provided encryption key and managed by the official Telegram client - [TDLib](https://core.telegram.org/tdlib).  
- All received audio files and their metadata are stored in `~/.local/share/rhythmbox/telegram` in an **unencrypted** format, you can clean it whenever you want. However, it's important to note that deleting these files will also remove them from the database. You can delete audio files from the plugin settings without compromising the integrity of the database.


## License

[Rhythmbox-Telegram](https://github.com/mervick/rhythmbox-telegram) is an open-source plugin distributed under the [GPL-3 license](https://github.com/mervick/rhythmbox-telegram/blob/master/LICENCE), ensuring that it remains freely accessible to all users and encouraging community collaboration and contribution.


## Contribute

If you like our plugin you can support the ongoing development and maintenance of Rhythmbox-Telegram by spreading the word about the plugin or making contributions via PayPal or cryptocurrency donations, ensuring its continued improvement and availability for the community.  

Your donations play a crucial role in supporting the development efforts, enabling the implementation of new features, bug fixes, and overall enhancements to ensure a seamless and enjoyable user experience for all. Every donation, no matter the amount, is deeply appreciated and directly contributes to the sustainability of the project.  

Click here to make a donation and show your support.

