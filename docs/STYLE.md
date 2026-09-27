# Style

This file wins over an AI suggestion. Read generated code before keeping it. Start small.

## Layout

- 4 spaces. No tabs.
- Python names: `snake_case` for functions and modules, `PascalCase` for types.
- One job per module. The tax engine does not call a model, the network, or the UI.

## Money and dates

- Rupiah amounts are `int`. No floats.
- Tax uses the rate stored in the ruleset file, with floor division.
- Dates are calendar dates (`YYYY-MM-DD`), already in Asia/Jakarta. Do not pass timestamps.

## Docstrings

Every public module, type, and function says what it is responsible for. Write it so you can understand it next month. Skip essays.

## Docs

README is required. Add more docs only when the project needs them.

## Tests

A figure on a screen must already have a test. Do not treat a passing chat reply as a tax result.
