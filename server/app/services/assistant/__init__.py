"""App-aware, read-only chat assistant.

A Claude tool-using agent (pattern modeled on ClearLink's "Charlie") that
answers questions by invoking OPA's own READ endpoints as tools. Tool calls
execute in-process against the real API, forwarding the signed-in user's
identity, so RBAC and validation are reused — never re-implemented.
"""
