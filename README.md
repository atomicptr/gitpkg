# gitpkg

A git powered package manager built on top of submodules.

## Install

The recommended way to install git-pkg is via [pipx](https://pypa.github.io/pipx/):

```bash
$ pipx install gitpkg
```

## Usage

The first thing you need to do to make your project work with git pkg is add a
destination. A destination is a place where your packages will be installed into,
you can have multiple of these.

Install a destination by using:

```bash
$ git pkg dest:register addons
```

The directory does not have to exist, it will be automatically generated.

Next we need to install packages lets do so by:

```bash
$ git pkg add https://github.com/coppolaemilio/dialogic
```

But wait! While we now have an addons/dialogic directory, the thing we actually
wanted there is now at addons/dialogic/addons/dialogic

Many projects, in this case Godot projects have the thing that is important to us
in a subdirectory, to have this subdirectory in the desired location we have
to define it as the package root by:

```bash
# You can just re-run this it will reconfigurate the package
$ git pkg add https://github.com/coppolaemilio/dialogic --package-root addons/dialogic
# OR: short hand
$ git pkg add https://github.com/coppolaemilio/dialogic -r addons/dialogic
```

Nice! But what do I do if the repository name and the directory I want is different?

Lets look at the next example:

```bash
$ git pkg add https://github.com/viniciusgerevini/godot-aseprite-wizard.git -r addons/AsepriteWizard
```

While this again will add addons/godot-aseprite-wizard we want the directory name to be
AsepriteWizard we can do this by:

```bash
$ git pkg add https://github.com/viniciusgerevini/godot-aseprite-wizard.git -r addons/AsepriteWizard --name AsepriteWizard
# OR:
$ git pkg add https://github.com/viniciusgerevini/godot-aseprite-wizard.git --package-root-with-name addons/AsepriteWizard
# OR: actual shorthand
$ git pkg add https://github.com/viniciusgerevini/godot-aseprite-wizard.git -rn addons/AsepriteWizard
```

Oh no! Now we have addons/godot-aseprite-wizard and addons/AsepriteWizard... why?
Names are essential for identifying projects so this can not be updated, we just have to remove
the unwanted package now:

```bash
$ git pkg remove godot-aseprite-wizard
```

Nice! Now we can finally get back to work!

A few days later...

It looks like the packages received some updates! To update all installed packages simply run:

```bash
$ git pkg update
# You can also update singular packages by providing their names
$ git pkg update dialogic AsepriteWizard
```

Since this is powered by git submodules, you have to commit the update.

## Motivation

Managing other git repositories as dependencies is essentially a very good idea
but git submodules are a pain to work with so there came the idea of having a 
simpler approach that feels more like using something like npm, composer etc.

I mostly wrote this to use this in Godot projects to manage the addons I install
but quickly realized this can be used for a lot of programming languages where
package managers are not an option.

This is essentially just an opinionated wrapper around git and git submodules.

## License

GNU General Public License v3

![](https://www.gnu.org/graphics/gplv3-127x51.png)