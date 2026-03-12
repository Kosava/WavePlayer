# WavePlayer

Modern modular media player built with **Python, Qt6 and mpv**.

WavePlayer focuses on **performance, extensibility and clean architecture**.
The project uses a **plugin-based system** that allows new features to be added without modifying the core player.

It is designed as a **modern, extensible alternative to traditional media players**, with built-in support for streaming, subtitles, torrents and metadata plugins.

---

# Features

## Core Player

* MPV powered playback engine
* Hardware accelerated decoding
* Smooth seeking
* Playlist support
* Resume playback
* Modern Qt interface
* Customizable themes

## Subtitle System

* Automatic subtitle loading
* Subtitle search plugins
* Multiple subtitle providers
* Advanced subtitle styling
* Language preferences
* Subtitle synchronization tools

## Streaming

* YouTube streaming (via yt-dlp)
* Torrent streaming (via libtorrent)
* HTTP / network streams
* Playlist streaming

## Plugin System

WavePlayer supports a **modular plugin architecture**.

Plugins can provide:

* subtitle search
* metadata providers
* streaming sources
* UI extensions
* tools

Plugins are discovered and loaded dynamically at runtime.

## Media Library

Organize your movies and music with:

* watch history
* resume playback
* automatic media scanning
* series / episode detection
* recently watched list

---

# Architecture

WavePlayer is designed with a **layered architecture** separating UI, core logic and plugins.

```
WavePlayer
│
├── app.py
│
├── core
│   ├── mpv_engine.py
│   ├── torrent_engine.py
│   ├── interfaces.py
│   ├── config.py
│   └── media_info.py
│
├── ui
│   ├── main_window.py
│   ├── video_widget.py
│   ├── controls.py
│   ├── overlay.py
│   ├── playlist_panel.py
│   └── settings_dialog.py
│
├── plugins
│   ├── plugin_api.py
│   ├── plugin_manager.py
│   ├── subtitle_search.py
│   ├── tmdb_metadata.py
│   └── youtube_stream.py
│
└── requirements.txt
```

### Core Layer

Handles playback engines, torrent streaming and configuration.

### UI Layer

Qt-based interface for the player.

### Plugin Layer

Extends functionality without modifying the core application.

---

# Requirements

Python **3.10+**

Required Python packages:

* PyQt6
* python-mpv
* libtorrent
* yt-dlp

Install dependencies:

```
pip install -r requirements.txt
```

---

# System Dependencies

### Debian / Ubuntu

```
sudo apt install mpv python3-libtorrent
```

### Arch Linux

```
sudo pacman -S mpv python-libtorrent
```

### Fedora

```
sudo dnf install mpv python3-libtorrent
```

---

# Running WavePlayer

Run the player:

```
python app.py
```

Open a file directly:

```
python app.py movie.mkv
```

---

# Plugins

Plugins are located in the `plugins/` directory.

Each plugin must implement the `WavePlugin` interface.

Example plugin types:

| Type         | Description                   |
| ------------ | ----------------------------- |
| Subtitle     | Subtitle search and download  |
| Metadata     | Movie / TV metadata providers |
| Streaming    | Streaming sources             |
| Tool         | Utility plugins               |
| UI Extension | Additional interface features |

WavePlayer loads plugins dynamically at startup.

---

# Example Plugins

Included plugins:

### SubtitleSearch

Search subtitles from multiple providers.

### TMDb Metadata

Fetch movie and TV metadata from TheMovieDB.

### YouTube Streaming

Play YouTube videos directly inside the player.

### Media Library

Organize and manage local media collections.

---

# Configuration

Configuration files are stored in:

Linux

```
~/.config/WavePlayer/
```

The configuration file is:

```
config.json
```

This file stores:

* player settings
* subtitle preferences
* plugin configuration
* playback options
* torrent settings

---

# Roadmap

Planned features:

* plugin marketplace
* torrent search plugins
* Chromecast support
* DLNA streaming
* GPU shader support
* improved media library interface
* cross-platform packaging
* plugin auto-updates

---

# Contributing

Contributions are welcome.

You can contribute by:

* writing plugins
* fixing bugs
* improving UI
* improving documentation
* testing new features

Fork the repository and submit a pull request.

---

# Development Goals

WavePlayer aims to be:

* modular
* extensible
* lightweight
* developer-friendly

The architecture also allows porting the backend to **C++ or Rust** while keeping the same plugin system.

---

# License

MIT License

Copyright (c) 2026 WavePlayer

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction.

See the LICENSE file for full details.
