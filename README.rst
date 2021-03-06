==================================================================
Polyvers: Bump sub-project versions in Git monorepos independently
==================================================================

.. _opening-start:
.. image:: https://img.shields.io/pypi/v/polyvers.svg
    :alt: Deployed in PyPi?
    :target: https://pypi.org/pypi/polyvers

.. image:: https://img.shields.io/travis/ankostis/polyvers.svg
    :alt: TravisCI (linux) build ok?
    :target: https://travis-ci.org/ankostis/polyvers

.. image:: https://ci.appveyor.com/api/projects/status/lyyjtmit5ti7tg1n?svg=true
    :alt: Apveyor (Windows) build?
    :scale: 100%
    :target: https://ci.appveyor.com/project/ankostis/polyvers

.. image:: https://img.shields.io/coveralls/github/ankostis/polyvers.svg
    :alt: Test-case coverage report
    :scale: 100%
    :target: https://coveralls.io/github/ankostis/polyvers?branch=master&service=github

.. image:: https://readthedocs.org/projects/polyvers/badge/?version=latest
    :target: https://polyvers.readthedocs.io/en/latest/?badge=latest
    :alt: Auto-generated documentation status

.. image:: https://pyup.io/repos/github/ankostis/polyvers/shield.svg
    :target: https://pyup.io/repos/github/ankostis/polyvers/
    :alt: Dependencies needing updates?

.. image:: https://api.codacy.com/project/badge/Grade/11b2545fd0264f1cab4c862998833503
    :target: https://www.codacy.com/app/ankostis/polyvers_jrc
    :alt: Code quality metric

:version:       |version|
:updated:       |today|
:Documentation: https://polyvers.readthedocs.io
:repository:    https://github.com/ankostis/polyvers
:pypi-repo:     https://pypi.org/project/polyvers/, https://pypi.org/project/polyversion/
:keywords:      version-management, configuration-management, versioning, git, monorepos,
                tool, library
:copyright:     2018 JRC.C4(STU), European Commission (`JRC <https://ec.europa.eu/jrc/>`_)
:license:       `EUPL 1.2 <https://joinup.ec.europa.eu/software/page/eupl>`_

A Python 3.6+ command-line tool to manage `PEP-440 version-ids
<https://www.python.org/dev/peps/pep-0440/>`_ of dependent sub-projects
hosted in a *Git* :term:`monorepo`\s, independently.

The key features are:

- :term:`setuptools integration`,
- x2 :term:`repo scheme`\s (:term:`monorepo`, :term:`mono-project`),
- configurable :term:`version scheme`,
- *leaf* :term:`release scheme`,
- intuitive :term:`version-bump algebra` (TODO),
- configurable :term:`engravings`.

The *leaf version scheme* feature departs from the logic of :ref:`similar-tools`.
Specifically, when bumping the version of sub-project(s), this tool
adds **+2 tags and +1 commits**:

  - one :term:`Version tag` in-trunk like ``foo-proj-v0.1.0``,
  - and another :term:`Release tag` on a new :term:`out-of-trunk commit` (leaf)
    like ``foo-proj-r0.1.0`` (the new version-ids are :term:`engrave`\d only
    in this release-commit):

    .. figure:: _static/leaf_commits.png
        :align: center
        :alt: Leaf-commits & version/release tags for the two repo's sub-projects

        Leaf-commits & version/release-tags for the two sub-project's,
        as shown in this repo's git history.

.. Note::
  The reason for this feature is to allow exchange code across branches (for the
  different sub-projects) without :term:`engravings` getting in your way as
  merge-conflicts.

Additional capabilities and utilities:

- It is still possible to use plain **version tags (vtags)** like ``v0.1.0``,
  assuming you have a single project (called hereinafter a :term:`mono-project`)

- A separate Python 2.7+ **polyversion** project, which contains API to extract
  sub-project's version from past tags (provided as a separate subproject
  so client programs do not get ``polyvers`` commands transitive dependencies).
  The library functions as a :term:`setuptools  plugin`.

.. _opening-end:

.. contents:: Table of Contents
   :backlinks: top
   :depth: 4


.. _usage:

Tutorial
========
Install the tool
----------------
And you get the ``polyvers`` command:

.. code-block:: console

    $ pip install polyvers
    ...
    $ polyvers --version
    0.0.0
    $ polyvers --help
    ...

    $ polyvers status
    polyvers: Neither `setup.py` nor `.polyvers(.json|.py|.salt)` config-files found!

.. Note::
    Actually two projects are installed:

    - **polyvers** cmd-line tool, for developing python :term:`monorepo`\s,
    - **polyversion**: the base python library used by projects developed
      with *polyvers* tool, so that their sources can discover their subproject-version
      on runtime from Git.


Prepare project
---------------
Assuming our :term:`monorepo` project ``/monorepo.git/`` contains two sub-projects,
then you need enter the following configurations into your build files::

    /monorepo.git/
        +--setup.py               # see below for contents
        +--mainprog/__init__.py
        |                         from polyversion import polyversion, polytime
        |                         __version__ = polyversion()
        |                         __updated__ = polytime()
        |                         ...
        |
        +--core-lib/
            +--setup.py:          # like above
            +--core/__init__.py   # like above
            +--...

.. Tip::
    You may see different sample approaches for your setup-files by looking
    into both `polyvers` & `polyversion` subprojects of this repo (because
    they eat their own dog food).

The `polyversion` library function as a *setuptools* "plugin", and
adds a new ``setup()`` keyword ``polyversion = (bool | dict)``
(see :func:`polyversion.init_plugin_kw` for its content), which you can use it
like this:

.. code-block:: python

    from setuptools import setup

    setup(
        project='myname',
        version=''              # omit (or None) to abort if cannot auto-version
        polyversion={           # dict or bool
            'version_scheme: 'mono-project',
            ...  # See `polyversion.init_plugin_kw()` for more keys.
        },
        setup_requires=[..., 'polyversion'],
        ...
    )

.. Hint::
    The ``setup_requires=['polyvers']`` keyword  (only available with *setuptools*,
    and not *distutils*), enables the new ``polyversion=`` setup-keyword.

Alternatively, a subproject may use :pep:`0518` to pre-install `polyversion`
library *before* pip-installing or launching ``setup.py`` script.
To do that, add the ``pyproject.toml`` file below next to your `setup` script::

    [build-system]
    requires = ["setuptools", "wheel", "polyversion"]

and then you can simply import ``polyversion`` from your ``setup.py``:

.. code-block:: python

    from setuptools import setup
    from polyversion import polyversion

    setup(
        project='myname',
        version=polyversion(mono_project=True)  # version implied empty string.

.. Attention::
    To properly install a :pep:`0518` project you need ``pip-v10+`` version.


Initialize `polyvers`
---------------------
...we let the tool auto-discover the mapping of *project folders ↔ project-names*
and create a `traitlets configuration YAML-file <https://traitlets.readthedocs.io>`_
named as  ``/monorepo.git/.polyvers.py``:

.. code-block:: console

    $ cd monorepo.git

    $ polyvers init --monorepo
    Created new config-file '.polyvers.yaml'.

    $ cat .polyvers.yaml
    ...
    PolyversCmd:
      projects:
      - pname: mainprog     # name extracted from `setup.py`.
        basepath: .         # path discovered by the location of `setup.py`
      - pname: core
        basepath: core-lib
    ...

    $ git add .polyvers.yaml
    $ git commit -m 'add polyvers config-gile'

And now we can use the ``polyvers`` command to inspect the versions of all
sub-projects:

.. code-block:: console

    $ polyvers status
    - mainprog
    - core

Indeed there are no tags in in git-history for the tool to derive and display
project-versions, so only project-names are shown.  With ``--all`` option
more gets displayed:

.. code-block:: console

    $ polyvers status -a
    - pname: mainprog
      basepath: .
      gitver:
      history: []
    - pname: core
      basepath: core-lib
      gitver:
      history: []

..where ``gitver`` would be the result of ``git-describe``.


Bump versions
-------------
We can now use tool to set the same version to all sub-projects:

.. code-block:: console

    $ polyvers bump 0.0.0 -f noengraves   # all projects implied, if no project-name given
    00:52:06       |WARNI|polyvers.bumpcmd.BumpCmd|Ignored 1 errors while checking if at least one version-engraving happened:
      ignored (--force=noengraves): CmdException: No version-engravings happened, bump aborted.
    00:52:07       |NOTIC|polyvers.bumpcmd.BumpCmd|Bumped projects: mainprog-0.0.0 --> 0.0.0, core-0.0.0 --> 0.0.0

The ``--force=noengraves`` disables a safety check that requires at least one
file modification for :term:`engrave`\ing the current version in the leaf "Release" commit
(see next step).

.. code-block:: console

    $ polyvers status
    - mainprog-v0.0.0
    - core-v0.0.0

    $ git lg    # Ok, augmented `lg` output a bit here...HEAD --> UPPER branch.
    COMMITS BRANCH TAGS                 REMARKS
    ======= ====== ==================== ========================================
         O  latest mainprog-r0.0.0      - x2 tags on "Release" leaf-commit
        /          core-r0.0.0            outside-of-trunk (not in HEAD).
       O    MASTER mainprog-v0.0.0      - x2 tags on "Version" commit
       |           core-v0.0.0            for bumping both projects to v0.0.0
       O                                - Previous commit, before version bump.

   .. Hint::
      Note the difference between ``ABC-v0.0.0`` vs ``ABC-r0.0.0`` tags.

   In the source code, it's only the "release" commit that has :term:`engrave`\d* version-ids:

   .. code-block:: console

    $ cat mainprog/mainprog/__init__.py    # Untouched!
    import polyvers

    __title__     = "mainprog"
    __version__ = polyvers.version('mainprog')
    ...

    $ git checkout  latest
    $ cat mainprog/mainprog/__init__.py
    import polyvers

    __title__     = "mainprog"
    __version__ = '0.0.0'
    ...

    $ git checkout  -  # to return to master.


Engrave version in the sources
------------------------------
Usually programs report their version somehow when run, e.g. with ```cmd --version``.
With *polyvers* we can derive the latest from the tags created in the previous step,
using a code like this, usually in the file ``/mainprog/mainprog/__init__.py:``:

.. code-block:: python

    import polyvers

    __title__ = "mainprog"
    __version__ = polyvers.version('mainprog')
    ...

...and respectively ``/core-lib/core/__init__.py:``:

.. code-block:: python

    __version__ = polyvers.version('core')



Bump sub-projects selectively
-----------------------------
Now let's add another dummy commit and then bump ONLY ONE sub-project:

.. code-block:: console

    $ git commit  --allow-empty  -m "some head work"
    $ polyvers bump ^1 mainprog
    00:53:07       |NOTIC|polyvers.bumpcmd.BumpCmd|Bumped projects: mainprog-0.0.0 --> 0.0.1

    $ git lg
    COMMITS BRANCH TAGS                 REMARKS
    ======= ====== ==================== ========================================
         O  latest mainprog-r0.0.1.dev0 - The latest "Release" leaf-commit.
        /                                 branch `latest` was reset non-ff.
       O    MASTER mainprog-v0.0.1.dev0 - The latest "Version" commit.
       O                                - some head work
       | O         mainprog-r0.0.0      - Now it's obvious why "Release" commits
       |/          core-r0.0.0            are called "leafs".
       O           mainprog-v0.0.0
       |           core-v0.0.0
       O

    $ git checkout latest
    $ cat mainprog/mainprog/__init__.py
    import polyvers

    __title__     = "mainprog"
    __version__ = '0.0.1.dev0'
    ...

    $ cat core/core/__init__.py
    import polyvers

    __title__ = "core"
    __version__ = '0.0.0+mainprog.0.0.1.dev0'
    ...
    $ git checkout -

Notice how the the `"local" part of PEP-440
<https://www.python.org/dev/peps/pep-0440/#local-version-identifiers>`_ (statring with ``+...``)
is used by the engraved version of the **un-bumped** ``core`` project to signify
the correlated version of the **bumped** ``mainprog``.  This trick is not necessary
for tags because they apply repo-wide, to all sub-projects.


.. _features:

Features
========
.. include:: <xhtml1-lat1.txt>
.. glossary::

    PEP 440 version ids
        While most versioning tools use `Semantic versioning
        <http://semver.org/>`_, python's ``distutils`` native library
        supports the quasi-superset, but more versatile, `PEP-440 version ids
        <https://www.python.org/dev/peps/pep-0440/>`_, like that:

        - Pre-releases: when working on new features::

            X.YbN               # Beta release
            X.YrcN  or  X.YcN   # Release Candidate
            X.Y                 # Final release

        - Post-release::

            X.YaN.postM         # Post-release of an alpha release
            X.YrcN.postM        # Post-release of a release candidate

        - Dev-release::

            X.YaN.devM          # Developmental release of an alpha release
            X.Y.postN.devM      # Developmental release of a post-release

    version-bump algebra
        When bumping, the increment over the base-version can be specified with a
        "relative version", which is a combination of :pep:`0440` segments and
        one of these modifiers: ``+^~=``
        See :mod:`polyvers.vermath` for more.

    repo scheme
    monorepo
    mono-project
        whether a git repo hosts a single or multiple subprojects

        **Rational:**

        When your single project succeeds, problems like these are known only too well:

          Changes in **web-server** part depend on **core** features that cannot
          go public because the "official" **wire-protocol** is freezed.

          While downstream projects using **core** as a library complain about
          its bloated transitive dependencies (asking why *flask* library is needed??).

        So the time to "split the project" has come.  But from :term:`Lerna`:

          |laquo|\ Splitting up large codebases into separate independently versioned packages
          is extremely useful for code sharing. However, making changes across
          many repositories is messy and difficult to track, and testing across repositories
          gets complicated really fast.\ |Raquo|

        So a *monorepo* [#]_ [#]_ is the solution.
        But as `Yarn <https://yarnpkg.com/blog/2017/08/02/introducing-workspaces/>`_ put it:

          |laquo|\ OTOH, splitting projects into their own folders is sometimes not enough.
          Testing, managing dependencies, and publishing multiple packages quickly
          gets complicated and many such projects adopt tools such as ...\ |Raquo|

        *Polyvers* is such a tool.

        .. [#] <https://medium.com/@maoberlehner/monorepos-in-the-wild-33c6eb246cb9
        .. [#] http://www.drmaciver.com/2016/10/why-you-should-use-a-single-repository-for-all-your-companys-projects/

    version scheme
        the pattern for version-tags.
        2x2 *versioning schemes* are pre-configured, for :term:`mono-project` and
        :term:`monorepo` repositories, respectively:

        - `v1.2.3` (and `r1.2.3` applied on :term:`leaf commit`\s)
        - `project-v1.2.3` (and `project-r1.2.3` for :term:`leaf commit`\s)

    release scheme
    out-of-trunk commit
    leaf commit
    release tag
    r-tag
    version tag
    v-tag
        Even in single-project repos, sharing code across branches may cause
        merge-conflicts due to the version-ids :term:`engrave`\d" in the sources.
        In :term:`monorepo`\s, the versions proliferate, and so does the conflicts.

        Contrary to :ref:`similar-tools`, static version-ids are engraved only in out-of-trunk
        (leaf) commits, and only when the sub-projects are released.
        In-trunk code is never touched, and version-ids are reported, on runtime, based
        on Git tags (like ``git-describe``), so they are always up-to-date.

    engrave
    engravings
        the search-n-replace in files, to substitute the new version.
        Default grep-like substitutions are included, which can be re-configured
        in the ``.polyvers.yaml`` config file.

    setuptools
    setuptools plugin
    setuptools integration
        The `polyversion` library function as a *setuptools* "plugin", and
        adds a new ``setup()`` keyword ``polyversion = (bool | dict)``
        (see :func:`polyversion.init_plugin_kw` for its content).

    bdist-check
        When the ``setuptools:setup()`` keyword ``polyversion_check_bdist_enabled = True``
        the :term:`setuptools plugin` aborts any `bdist...` commands if they
        are not run from :term:`engrave`\d sources, (ie from an :term:`r-tag`).

        To enable this check without editing the sources, add the following into
        your ``$CWD/setup.cfg`` file::

            [global]
            polyversion_check_bdist_enabled = true
            ...

    Marking dependent versions across sub-projects
        [TODO] When bumping the version of a sub-project the `"local" part of PEP-440
        <https://www.python.org/dev/peps/pep-0440/#local-version-identifiers>`_
        on all other the *dependent* sub-projects in the monorepo  signify their relationship
        at the time of the bump.

    Lock release trains as "developmental"
        [TODO] Specific branches can be selected always to be published into *PyPi* only as
        `PEP-440's "Developmental" releases
        <https://www.python.org/dev/peps/pep-0440/#developmental-releases>`_, meanining that
        users need ``pip install --pre`` to install from such release-trains.
        This is a safeguard to avoid accidentally landing half-baked code to users.

    default version env-var
        From which env-var to read a project's *version* if git cmd fail.
        It does not override any value given as ``default_version`` keyword
        for :func:`polyversion.polyversion()`.
        Also :func:`polyversion.polytime()` assumes keyword ``no_raise=True``
        if such env-var is found.
        [Default var-name: ``<pname>_VERSION``]

    Other Features
        - Highly configurable using `traitlets <https://traitlets.readthedocs.io>`_,
          with sensible defaults; it should be possible to start using the tool
          without any config file (see `init` cmd), or by adding one of the flags
          ``--monorepo``/``--mono-project`` in all commands, in the face of
          conflicting tags.
        - Always accurate version reported on runtime when run from git repos
          (never again wonder with which version your experimental-data were produced).


Known Limitations, Drawbacks & Workarounds
------------------------------------------
.. TODO: epoch vermath, and update README

- PEP440 `Epoch` handling is not yet working.
- Version-bump's grammar is not yet as described in "GRAMMAR" section
  of command's doc::

    $ polyvers config desc --class BumpCmd
    BumpCmd(_SubCmd)
    ----------------
    Increase or set the version of project(s) to the (relative/absolute) version.
    SYNTAX:
        polyvers config desc [OPTIONS] <version> [<project>]...
    - If no project(s) specified, increase the versions on all projects.
    - Denied if version for some projects is backward-in-time (or has jumped parts?);
      use --force if you might.
    VERSION: - A version specifier, either ABSOLUTE, or RELATIVE to the current
    version og each project:
      - *ABSOLUTE* PEP-440 version samples:
        - Pre-releases: when working on new features:
            X.YbN               # Beta release
            X.YrcN  or  X.YcN   # Release Candidate
            X.Y                 # Final release
    ...

- (not related to this tool) In ``setup.py`` script, the kw-argument
  ``package_dir={'': <sub-dir>}`` arg is needed for `py_modules` to work
  when packaging sub-projects (also useful with ``find_packages()``,
  check this project's sources).
  But ``<sub-dir>`` must be relative to launch cwd, or else,
  ``pip install -e <subdir>`` and/or ``python setup.py develop``
  break.

- (not related to this tool) When building projects with ``python setup.py bdist_XXX``,
  you have to clean up your build directory (e.g. ``python setup.py clean --all``)
  or else, the distribution package will contain the sources from all previous
  subprojects built.  That applies also when rebuilding a project between versions.

- Installing directly from git-repos needs an engraved branch (e.g. ``latest``)::

      pip install git+https://github.com/ankostis/polyvers@latest

  If you still want to install non-engraved branhces (e.g. ``master``),
  set the :term:`default version env-var`; for example, since *polyvers* subproject
  has not customized the name of its env-var, you may install the very latest
  like this::

      polyvers_VERSION=1.2.3 pip install git+https://github.com/ankostis/polyvers

  .. Attention::
    The version given in the env-var is irrelevant.
    The installed version will still derive from git tags, and the local-part
    from the actual git-commit.

- (not related to this tool) If you don't place a ``setup.py`` file at the root
  of your git-repo (using ``package_dir`` argument to ``setup()``  function or
  in ``find_packages()``,  according to `setuptools-docs
  <http://setuptools.readthedocs.io/en/latest/setuptools.html#id10>`_), then
  in order to ``pip install git+https://...`` directly from remote URLs
  you have to use `this official trick
  <https://pip.pypa.io/en/stable/reference/pip_install/#vcs-support>`_.
  For example, to install *polyversion* subproject::

      pip install "git+https://github.com/ankostis/polyvers@latest#egg=polyversion&subdirectory=pvlib"

  Notice that the quotes are needed to escape the ``&`` char from bash.
  Respectively, use this to install from the very latest::

      polyversion_VERSION=1.2.3 pip install git+https://github.com/ankostis/polyvers#egg=polyversion&subdirectory=pvlib"


- Set branch ``latest`` as default in GitHub to show :term:`engrave`\d sub-project version-ids.

- See :ref:`to-dos`.

Recipes
=======
Automatically sign tags:
------------------------
Add this to your ``~/.polyvers.yaml``:

.. code-block:: yaml

    BumpCmd:
      sign_tags: true
      sign_user: <username-or-keyid>


.. _contribute-section:
.. _similar-tools:

Similar Tools
=============
Bumped across these projects while building it...

.. glossary::

    bumpversion
        The original **bumpversion** project; development stopped after 2015:
        (recomended also by :term:`python guide`)
        https://github.com/peritus/bumpversion

    bump2version
        active clone of the original:
        https://github.com/c4urself/bump2version

    releash
        another :term:`monorepo`\s managing tool, that publishes also to PyPi:
        https://github.com/maartenbreddels/releash

    Git Bump
        bump version using git-hooks:
        https://github.com/arrdem/git-bump

    Lerna
        A tool for managing JavaScript projects with multiple packages.
        https://lernajs.io/

    Pants
        a build system designed for codebases that:
        - Are large and/or growing rapidly.
        - Consist of many subprojects that share a significant amount of code.
        - Have complex dependencies on third-party libraries.
        - Use a variety of languages, code generators and frameworks.
        - https://www.pantsbuild.org/

    pbr
        a ``setup_requires`` library that
        injects sensible default and behaviors into your *setuptools*.
        Crafted for *Semantic Versioning*, maintained for OpenStack projects.
        https://docs.openstack.org/pbr/

    Zest.releaser
        easy releasing and tagging for Python packages; make easy, quick and
        neat releases of your Python packages.  You need to change the version number,
        add a new heading in your changelog, record the release date, svn/git/bzr/hg tag
        your project, perhaps upload it to pypi... *zest.releaser* takes care
        of the boring bits for you.
        (recomended also by :term:`python guide`)
        http://zestreleaser.readthedocs.io/

    incremental
        a small *setuptools* plugin library that versions Python projects.
        https://github.com/twisted/incremental

    changes
        Manages the release of a Python Library (intuitive logo,
        recomended also by :term:`python guide`):

        - Auto generates changelog entries from commit messages
        - CLI that follows Semantic Versioning principles to auto-increment the library version
        - Runs the library tests
        - Checks the package installation from a tarball and PyPi
        - Uploads the distribution to PyPi
        - Tags the GitHub repository

        https://github.com/michaeljoseph/changes

    setuptools_scm
        managing versions in scm metadata instead of declaring them as
        the version argument or in a scm managed file, apart from  handling
        file finders for the supported scm’s.
        (recomended also by :term:`python guide`)
        https://pypi.org/project/setuptools_scm/

        .. Note:
            Interesting how this project parses ``git describe`` tags:
            https://pypi.org/project/setuptools_scm/#default-versioning-scheme

    Dunamai
        Library and command line tool for producing dynamic, standards-compliant version strings, 
        derived from tags in your version control system. Suitable for projects written in 
        any programming language (i.e. no need for  `setup.py`), 
        many VCSs(Git; Mercurial, Darcs, Subversion, Bazaar), and 
        many Version styles (PEP 440, Semantic Versioning, Haskell Package Versioning Policy, Custom)
         https://github.com/mtkennerly/dunamai

    setupmeta
        Helper for simple `setup.py` files with *setuptools_scm* like tag-based versioning
        plus commands for bumping version, explain meta infos, cleanall, twine, etc
        https://github.com/zsimic/setupmeta

    python guide
        There is a dedicated guide for this problem in pythons docs:
        https://packaging.python.org/guides/single-sourcing-package-version/

Find more than `34 similar projects in GitHub:
<https://github.com/search?l=Python&o=desc&q=bump+version&s=updated&type=Repositories>`_
and in awesome: https://github.com/korfuri/awesome-monorepo.




Credits
=======
- Contains a function from the BSD-tool :term`pbr` to fetch version from *pkg-metadata*
  when invoked as a :term:`setuptools plugin` from inside an egg.

- This package was created with Cookiecutter_ and the `audreyr/cookiecutter-pypackage`_ project template.

- Using `towncrier <https://pypi.org/project/towncrier/>`_ for generating CHANGES.

.. _Cookiecutter: https://github.com/audreyr/cookiecutter
.. _`audreyr/cookiecutter-pypackage`: https://github.com/audreyr/cookiecutter-pypackage
