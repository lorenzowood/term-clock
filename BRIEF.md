# Term Clock

Write a clock program that could be used over SSH (or just in a terminal).

When you invoke it from the command line, it should use available terminal space to display a digital clock in the format

hh:mm:ss

that stays up to date. It should make it as big as possible, so:

* If there are less than seven text lines available, just display a text clock centred vertically and horizontally
* If there are more than seven text lines available, draw the numbers and colon using ASCII art. You pick: 7-segement style, or 5×7 matrix using blocks
* Make sure the rendered clock digits fill the available area as far as possible while retaining their aspect ratio

CTRL+C should exit and return to the CLI prompt.

Use strict TDD:
* Write tests
* See tests fail
* Write code
* See tests pass
* Refactor as you go

Make sure this design process is documented as you go.
