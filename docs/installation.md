DroneCOT's functionality provided by a command-line program called `dronecot`.

There are several methods of installing DroneCOT. They are listed below, in order of complexity.

## Debian, Ubuntu, Raspberry Pi

Install DroneCOT, and prerequisite packages of [PyTAK](https://pytak.rtfd.io).

```sh linenums="1"
sudo apt update
wget https://github.com/ampledata/pytak/releases/latest/download/python3-pytak_latest_all.deb
sudo apt install -f ./python3-pytak_latest_all.deb
wget https://github.com/ampledata/dronecot/releases/latest/download/python3-dronecot_latest_all.deb
sudo apt install -f ./python3-dronecot_latest_all.deb
```

## Windows, Linux

Install from the Python Package Index (PyPI) [Advanced Users]::

```sh
sudo python3 -m pip install dronecot
```

## Developers

PRs welcome!

```sh linenums="1"
git clone https://github.com/snstac/dronecot.git
cd dronecot/
python3 setup.py install
```
