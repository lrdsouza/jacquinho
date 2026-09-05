'''Shared scaffolding for every MCP server in this project.'''

from __future__ import annotations

from abc import ABC, abstractmethod

from fastmcp import FastMCP

from ..config import Settings


class BaseMCP(ABC):
    '''One bounded slice of the domain, exposed as a mountable FastMCP server.

    Subclasses declare a name and instructions, then register their tools in
    :meth:`register`. The instructions matter: they are how behaviour reaches
    the agent now that this project uses no Hermes skills.
    '''

    name: str = 'base'
    instructions: str = ''

    def __init__(self, settings: Settings):
        self.settings = settings
        self.mcp: FastMCP = FastMCP(name=self.name, instructions=self.instructions)
        self.register()

    @abstractmethod
    def register(self) -> None:
        '''Attach tools, resources and prompts to ``self.mcp``.'''

    @property
    def server(self) -> FastMCP:
        return self.mcp
