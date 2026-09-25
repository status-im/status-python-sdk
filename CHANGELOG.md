# Changelog

All notable changes to `status-python-sdk` will be documented in this file. The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.2.1] - 2026-09-25

### Changed

- `def download_build_and_launch`
    - A `launcher` can be passed to launch a [status-go] build that is already on disk, skipping the release download and extraction
    - The path of the launched build is now returned

## [1.2.0] - 2026-09-22

### Added

- Build and launch [status-go] locally / inside already existing Docker container. Requires [nix] and [git] set up. 
- Download build and launch [status-go] locally / inside already existing Docker container.
- `class Account` has new property `status_go_commit_sha`

### Fixed

- Image RPC call for getting the current `profile_picture` returned `None` instead of an empty `list`.
- If no `commit` is passed to `launch_docker_container`, the latest commit from the `develop` branch is now used.

### Removed

- Remove `can_post` check when sending community messages, reducing RPC calls to [status-go] to prevent it from crashing under heavy use. A custom error is now raised instead if the user lacks privileges to send messages in the channel.

## [1.1.6] - 2026-09-09

### Fixed

- Real time
    - `def listen_messages` monitors [status-go] property `messages` only instead of `messages` and `chats`
    - Unfiltered messages will return `dict` only instead of `dict` or `list[dict]`

## [1.1.5] - 2026-09-09

### Fixed

- Real time
    - `def listen_messages` returns a single `Message` with multiple images, instead of a `Message` per image
    - Remove duplicated [status-go] signals that have already been yielded

## [1.1.4] - 2026-09-09

### Added

- Real time
    - User removes the account from their contacts
    - Listen for bridged messages
- `class Channel`
    - move position up and down
    - change current category
    - add and delete member permissions
- Send bridged messages
    - `class Account`
    - `class GroupChat`
    - `class Channel`

### Fixed

- `account.add_contact` accepting a friend request via `wakuext_addContact` no longer sends the user "Please add me to your contacts."
- Sending a reply to a message returns the ID of the sent message instead of the replied-to message's ID
-  `docker-compose.yaml` ENV parameters match the ones used in `launch_docker_container`
- Data class `Message` supports bridged messages
- `listen_messages` would break if an unhandled `content_type` was found

### Removed

- `class Logger` has been deprecated. Logger config must be set outside of `status-sdk` with `logging.basicConfig`.

### Changed

- Property `state` in data class `CommunityRequest` has been replaced with boolean values `pending`, `reject`, `accept` and `cancel`.

## [1.1.3] - 2026-08-26

### Added

- Emoji Reactions
    - `class Account`
    - `class GroupChat`
    - `class Channel`
- Real time
    - Listen for message mentions
    - Accepted contact requests

### Changed

- Real time listening will return custom `dataclass` instead of `dict`
- Internal `class Signal` can now listen for multiple signal types at once, or leave them unfiltered to listen for all

## [1.1.2] - 2026-08-18

### Added

- Block / Unblock contacts from `class Account`

### Changed

- Deleted messages would be flagged as deleted but not removed from the internal [status-go] database.
- `class Account` no longer logs out an already logged in account on initialization. Calling `def login` with the same account continues normally; calling it with a different account logs out the original one first.
- `get_messages` supports `str` in format `YYYY-MM-DD`

## [1.1.1] - 2026-08-12

### Added

- Send images
    - `class Account`
    - `class GroupChat`
    - `class Channel`
- Listen for new contact requests in real time
- Swap Community Control Nodes between Status App and [status-go]
    - New `launch_docker_container` property
    - Add `data_folder` to `class Community`
- Get community collectables

### Fixed

- Centre `profile_picture` when setting the value

### Changed

- `login` functionality in `class Account` supports Keccak-256 hash if the `data` folder has been copied over from another Status instance ([status-go] or Status App)

will try to log in without a hashed password

## [1.1.0] - 2026-08-04

### Added

- Convert Chat Key (`compressed_key`) and URL (`url`) to Status App `public_key`
- Get and set current status of the logged in account
- Support async signal fetching
- Sync `status-im/status-python-sdk` with Status App via **Installation ID**
- Create `class GroupChat`
    - Create chat
    - Leave chat
    - Edit chat name
    - Edit Group Picture
    - Add member
    - Remove member
    - Get current chat members
    - Support messaging similar to `class Account`
- Create `class Community`
    - Kick member
    - Ban member
    - Unban previously banned members
    - Leave
    - Accept new member
    - Decline new member
    - Get members
    - Current channels (community chats)
- Create `class Channel`
    - Create chat
    - Delete chat
    - Get messages
    - Send messages
    - Delete messages
    - Properties
        - Name - get and set
        - Colour - get and set
        - Description - get and set
        - Emoji - get and set


### Removed

- `class Account` properties
    - `community_members`

## [1.0.0] - 2026-07-15

### Added

- Create initial design of `class Account`
    - Create account
    - Log in
    - Account recovery - load and create `.bkp` files
    - Log out
    - Send friend request
    - Accept friend request - when the bot and the user have sent a friend request
    - Decline friend request
    - Send community join request
    - Messaging
        - Read messages from given start and end timestamps
        - Read new messages in real time
        - Send message
    - Properties
        - Overall account information
        - Contacts the bot has seen
        - Communities the bot has access to
        - Chats the bot has access to
        - Display Name - get and set
        - Bio - get and set
        - Profile Picture - get and set
    - Wallet
        - Get account balance
        - Get market information
        - Get transactions
        - Send crypto
        - Swap crypto
            - ETH to ERC-20
            - ERC-20 to ETH
            - ERC-20 to ERC-20
- Launch [status-go] Docker container with Python instead of manual `docker compose up -d` setup.
- Custom library errors

[1.2.1]: https://github.com/status-im/status-python-sdk/releases/tag/1.2.1
[1.2.0]: https://github.com/status-im/status-python-sdk/releases/tag/1.2.0
[1.1.6]: https://github.com/status-im/status-python-sdk/releases/tag/1.1.6
[1.1.5]: https://github.com/status-im/status-python-sdk/releases/tag/1.1.5
[1.1.4]: https://github.com/status-im/status-python-sdk/releases/tag/1.1.4
[1.1.3]: https://github.com/status-im/status-python-sdk/releases/tag/1.1.3
[1.1.2]: https://github.com/status-im/status-python-sdk/releases/tag/1.1.2
[1.1.1]: https://github.com/status-im/status-python-sdk/releases/tag/1.1.1
[1.1.0]: https://github.com/status-im/status-python-sdk/releases/tag/1.1.0
[1.0.0]: https://github.com/status-im/status-python-sdk/releases/tag/1.0.0

[nix]: https://nixos.org/
[git]: https://git-scm.com/
[status-go]: https://github.com/status-im/status-go
[status-backend]: https://github.com/status-im/status-go
