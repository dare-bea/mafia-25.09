import mafia.normal as n

with open('README.md', 'w') as f:
    f.writelines([
        "# Mafia Party Game\n",
        "Implements extendable classes to create your own roles and factions\n",
        "in `mafia.core`, and also a collection of frequently used roles, \n",
        "modifiers, and factions in `mafia.normal`.\n",
        "\n",
        "## Normal Definitions\n",
        "\n",
        "### Roles\n"
        "\n",
        *(f"* {i} (`{x.__module__}.{x.__qualname__}`)\n"
          for i, x in n.ROLES.items()),
        "\n",
        "### Combined Roles\n"
        "\n",
        *(f"* {i} (`{x.__module__}.{x.__qualname__}`)\n"
          for i, x in n.COMBINED_ROLES.items()),
        "\n",
        "### Modifiers\n"
        "\n",
        *(f"* {i} (`{x.__module__}.{x.__qualname__}`)\n"
          for i, x in n.MODIFIERS.items()),
        "\n",
        "### Alignments & Factions\n"
        "\n",
        *(f"* {i} (`{x.__module__}.{x.__qualname__}`)\n"
          for i, x in n.ALIGNMENTS.items()),
    ])