# sic documentation pages

Suggested method of generating html out of the markdown files:

```shell
pandoc -s --toc < docs/main.md > main.html
```

Then copy only the `<body>` content of `main.html` into the content of a documentation flat page, ensuring it's all wrapped in an `<article>` element.
