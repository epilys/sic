# User Documentation

## Creating An Account

### Plain signup

#### Vouching

### Get an invite

### Make an invite request

## Posting

### Tags and all that

#### How to add/edit tags

### Tag aggregations (topics)

#### How to create your own

### Commenting

## Configuring your account

### Profile (Avatar, metadata)

### Bookmarks

### SSH login

As an alternative to authentication with a password, you can use one time passwords with your SSH keys. The following process is required:

1. add your SSH public key to your account under "Edit Settings"
2. next time you want to login, on the login page, click on "Sign in with your SSH key instead"
3. you will be presented with a small random string challenge that you have to sign with the proper SSH private key. An example command line incantation to generate a signature for the challenge `8d408684fd` and key `~/.id_rsa` is:
   
   ```shell
   printf '8d408684fd' | ssh-keygen -Y sign -f ~/.ssh/id_rsa -n sic | xclip -selection clipboard
   ```
   
   `xclip` will copy the signature in your system clipboard.
4. Paste the signature within the short time window in the form and log in.

_Note_: signing with `ssh-keygen` requires a recent enough version of it.

### Notifications and Messages

### other settings

## Inviting other people

### Vouching

## Accessing other interfaces

### RSS/Atom, default and personalised

### Available web APIs

- The `all stories` frontpage is available in JSON by appending `/json/` to the end of the URL. Examples:
  - `https://tade.link/all/json/`
  - `https://tade.link/all/page/2/json/`
- A cached version of a submitted url might be available. Append `/cached` to story url to retrieve it. There might also be a formatted version of it under `/cached/formatted/`. Examples:
  - `https://tade.link/s/146/improving-the-world-bit-by-expensive-bit-mythic-beasts/cached/`
  - `https://tade.link/s/146/improving-the-world-bit-by-expensive-bit-mythic-beasts/cached/formatted/`
- You can retrieve a post as an email (as it might have been sent via the mailing list):
  - for stories, append `/rfc5322/` at the url.
  - For comments: click source view, and replace `source` from url to `rfc5322` in the URL.
  Examples:
  - https://tade.link/s/146/improving-the-world-bit-by-expensive-bit-mythic-beasts/rfc5322/
  - https://tade.link/s/134/friendly-computers-starting-my-own-computer-co-operative/rfc5322/167/

### TOR

### Mailing list mode

#### Set the required settings

#### How to post/reply to the list and threads

### NNTP server

NNTP is a very old protocol used to distribute "articles" to users, much like a mailing list. The community has an experimental NNTP bridge that exposes posts to NNTP.

#### How to connect with your client

Connect to the site's url in the port `563`, i.e. `tade.link:563`. If your client allows authentication, you can optionally log in with your account. The server is read-only for unathenticated users.

#### How to post/reply

Posts via NNTP must use NNTP. It is possible to reply via the mailing list also, though. To set the metadata of your post use the following NNTP headers:

- `Tags:`, comma separated. Example: `Tags: meta, programming`
- `URL:`
- `Content-Warning:`
- etc.

## Community documents

- Community Code of Conduct
- Privacy Policy
- Contact the admins
- Community statistics
