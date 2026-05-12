  # Requirements â Markdown Previewer

  ## What to build
  A single-page web app with a split-pane layout: markdown editor on the left, live HTML preview on the right.

  ## Features
  - Text area on the left where user types raw markdown
  - Live preview panel on the right that updates as user types
  - Support headings, bold, italic, lists, links, and code blocks
  - Clear button that resets both panes
  - Preloaded with example markdown content on first load

  ## Tech
  - Plain HTML, CSS, JavaScript â no framework required
  - Single file output: index.html
  - Use marked.js from CDN for markdown parsing
  - Must work in Chrome without any build step

  ## Acceptance criteria
  - Typing markdown on the left updates the preview in real time
  - All 6 markdown elements render correctly (headings, bold, italic, lists, links, code)
  - Clear button resets both panes
  - Page loads with example content already shown
  - No console errors on load or interaction
  - Page is usable on a 375px wide mobile screen
