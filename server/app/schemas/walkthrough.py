"""Walkthrough (new-user product tour) schemas.

A *walkthrough* is an ordered list of spotlight steps tailored to (app, role).
The backend is the single source of truth for the copy and ordering; the
frontend renders it with one shared spotlight engine. See
`services/walkthrough_service.py` for how tours are composed from reusable
fragments, and `client/src/components/walkthrough/` for the renderer.
"""
from typing import List, Optional
from pydantic import BaseModel


class TourAppLink(BaseModel):
    """A cross-app deep link surfaced inside a step (e.g. 'Open ClaimGuard').

    Only emitted for apps the current user can actually reach, so the outro
    'here's the rest of the suite' step never dangles a link the user is
    walled out of.
    """
    app: str            # AppKey the frontend knows: payguard|claimguard|siu|iam|assistant
    label: str
    path: str = ""      # optional sub-path within that app


class TourStep(BaseModel):
    key: str                                # stable id, unique within the tour
    title: str
    body: str                               # one or two short sentences
    anchor: Optional[str] = None            # data-tour="<anchor>" to spotlight; None => centered card
    placement: str = "auto"                 # top|bottom|left|right|center|auto (positioning hint)
    route: Optional[str] = None             # in-app path to navigate to before showing this step
    app_links: List[TourAppLink] = []       # cross-app buttons (outro / suite steps)


class Tour(BaseModel):
    app: str                                # which app this tour is for
    role: str                               # the persona the tour was tailored to
    role_label: str                         # human label for that persona, e.g. "Analyst"
    version: int = 1                        # bump to re-show a completed tour after a redesign
    steps: List[TourStep]
