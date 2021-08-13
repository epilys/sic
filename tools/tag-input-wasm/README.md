# 'tag-input-wasm'

A `<select>` helper for post tag selection used in the form to submit/edit
posts. See `src/lib.rs` for code comment annotations.

## Build

```shell
wasm-pack build --target web --release
```

And place the files `pkg/tag_input_wasm_bg.wasm`, `pkg/tag_input_wasm.js` in
the static files directory.
