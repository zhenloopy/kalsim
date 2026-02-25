This repo is a project to design a feasible risk book for prediction market portfolios such as Kalshi and Polymarket. For now, it should just use Kalshi and any instructions related to both should just use Kalshi and Polymarket will be integrated later.

This project involves a fair amount of rigorous financial + mathematical code. The most important things for the assumptions are:
- keep assumptions to a minimum
- keep functionality and algorithms as simple as they can be, but do not avoid complexity on genuinely complicated sections if it leads to a better accuracy

Work in Python. Do not repeat functionality and compose the repo and code into logical sections based on use. The project should be mostly backend work with a simple GUI implemented at the end so the user can look at what the backend is doing. Do not write comments except very high level to outline what a large section is doing.

Focus on simplicity, speed, and accuracy to how risk is tracked in real life. Commit separate features early and often. Any testing should have a basis in math / a known good solution, so do not test obvious functions and instead test core pieces of the workflow or tricky algorithms with nuanced states and edge cases. There should be tests but they should not be useless.

Update and install any tools you need. Use a venv and make sure it's sourced before pip installing or running anything.

Write important notes about the repo in a file NOTES.md. This should include locations of core features and important architectural decisions and why they were made. This can also point to more specific documentation which you can create near the features themselves in case a feature is particularly nuanced or complex. Write notes often after changes, but only write them if changes are substansial. The first place you turn for repo guidance should be the NOTES.md.
