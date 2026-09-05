'''MCP surface for her opinions on dishes and the launch menu itself.'''

from __future__ import annotations

from typing import Annotated

from pydantic import Field

from ..domain.catalogue import CatalogueUnavailable as MemoryUnavailable
from ..domain.catalogue import DishFeedbackStore, LaunchMenuStore
from .base import BaseMCP


class MenuMCP(BaseMCP):
    '''Carries a dish from her opinion of it to the launch menu.'''

    name = 'menu'
    instructions = (
        'Every candidate dish gets record_feedback before anything else: does she '
        'want to cook it, and does she see a problem with it. A dish she dislikes '
        'is dead however good the numbers look. Only add_dish once the gate '
        'passed, the CMV is complete, the price is market-grounded and she chose '
        'it. build_launch_menu is the deliverable the whole conversation is for.'
    )

    def __init__(self, settings, db):
        self.feedback = DishFeedbackStore(db)
        self.menu = LaunchMenuStore(db)
        super().__init__(settings)

    def register(self) -> None:
        @self.mcp.tool
        def record_feedback(
            dish: Annotated[str, Field(description='Dish you showed her.')],
            likes_cooking: Annotated[bool, Field(description='Does she actually want to cook this?')],
            comment: Annotated[str, Field(description='Her reaction, in her own words.')],
            impediments: Annotated[list[str], Field(description="Anything she flagged, e.g. ['da muito trabalho', 'nao tenho forma'].")] = [],
        ) -> dict:
            '''Record what she thinks of a dish you proposed.

            The brief asks this of every candidate: whether she likes cooking it
            and whether she sees an impediment. Her impediments are leads for
            kitchen_elicitation_gaps, not just notes.
            '''
            try:
                entry = self.feedback.record(dish, likes_cooking, comment, impediments)
            except MemoryUnavailable as error:
                return {'saved': False, 'error': str(error)}
            return {
                'saved': True,
                **entry,
                'next_step': (
                    "Call recipes_reject_candidate with reason 'disliked', then "
                    'recipes_next_candidate and offer her the next option. Do not '
                    'try to talk her into it.'
                    if not likes_cooking
                    else (
                        'She raised something. Take each impediment to '
                        'kitchen_elicitation_gaps; if it turns out to block the '
                        "dish, call recipes_reject_candidate with reason "
                        "'impediment' and move to recipes_next_candidate."
                        if impediments
                        else 'No impediment raised. Continue with the evaluate_dish '
                        'prompt.'
                    )
                ),
            }

        @self.mcp.tool
        def list_feedback() -> dict:
            '''Everything she has said about dishes so far.'''
            try:
                entries = self.feedback.all()
            except MemoryUnavailable as error:
                return {'available': False, 'error': str(error)}
            return {
                'available': True,
                'liked': [e['dish'] for e in entries if e['likes_cooking']],
                'rejected': [e['dish'] for e in entries if not e['likes_cooking']],
                'entries': entries,
            }

        @self.mcp.tool
        def add_dish(
            dish: Annotated[str, Field(description='Dish she accepted.')],
            category: Annotated[str, Field(description='Category id from dishes_list_categories.')],
            cmv: Annotated[float, Field(gt=0, description='CMV per portion from pricing_calculate_cmv.')],
            price: Annotated[float, Field(gt=0, description='The price SHE chose.')],
            confidence_band: Annotated[str, Field(description="Band from confidence_assess_answer: 'high', 'medium' or 'low'.")],
            notes: Annotated[str, Field(description='Anything she should remember about this dish.')] = '',
        ) -> dict:
            '''Put an accepted dish on the launch menu.

            Only after the viability gate passed, the CMV was complete, the price
            was grounded in the market, and she picked it herself.
            '''
            try:
                entry = self.menu.add(
                    dish, category, cmv, price, self.settings.platform_fee,
                    confidence_band, notes,
                )
            except MemoryUnavailable as error:
                return {'added': False, 'error': str(error)}
            return {'added': True, **entry}

        @self.mcp.tool
        def remove_dish(
            dish: Annotated[str, Field(description='Dish to take off the menu.')],
        ) -> dict:
            '''Take a dish off the launch menu.'''
            try:
                return {'removed': self.menu.remove(dish)}
            except MemoryUnavailable as error:
                return {'removed': False, 'error': str(error)}

        @self.mcp.tool
        def build_launch_menu() -> dict:
            '''The launch menu: every accepted dish, with cost, price and profit.

            This is where the consultation is meant to end. It flags any dish
            that got on with weak evidence.
            '''
            try:
                return {'available': True, **self.menu.summary()}
            except MemoryUnavailable as error:
                return {'available': False, 'error': str(error)}
