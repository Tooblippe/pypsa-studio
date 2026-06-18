
# CRITICAL RULES - MUST FOLLOW

## RESPONSES

- Keep responses concise and to the point - unless the user asks otherwise

## PLANNING MODE

- Always ask clarifying questions
- Never assume design, tech stack or features
- When planning changes to the react-flow canvas:
  - always think, warn or ask clatifying questions regarding expected behaviour and potential degradation of current fucntionality
  - the react-flow llms.txt is available https://reactflow.dev/llms.txt
- When planning State changes in reflex application:
  - ensure to apply the "yield" pattern not to block ui, see reflex llms.txt
  - the Reflex llms.txt is avilable at https://reflex.dev/docs/llms.txt
  - 

## CHANGE / EDIT MODE

- After completing features (large or small), always run commands like black to chcek formatting
- Always add docstrings to functions
- Always add type hints


## TESTING

- Just run `uv run reflex compile` to see if the app compiles as a test.

## MAIN COMPONENTS
-
- Reflex - Python based front and bakend web framework
- react-flow for the canvas, extended to work in Reflex

## SKILLS

- Reflex skills can be found here -https://reflex.dev/docs/ai/integrations/skills/


## LLMS
- Reflex llms.txt - https://reflex.dev/docs/llms.txt
- React-flow llms.txt - https://reactflow.dev/llms.txt
- 