# Development Setup

1. Install [Uv](https://docs.astral.sh/uv/#getting-started)
2. Install the project dependencies: `uv sync --locked --all-extras --dev`
3. To confirm that you can run Beets in its own isolated environment with Beets-audible from source: `uv run beet -v version`

   If `audible` is not in the list of plugins shown, add it to the list of plugins in the Beets configuration file. See the readme for instructions.

Warning: installing the beets-copyartifacts3 plugin in development breaks the ability to run Beets-audible from source, I'm unsure why this only happens in development. I've seen this happening with other plugins, so this isn't specific to beets-audible.
