# 'tag-input-wasm'

A `<select>` helper for post tag selection used in the form to submit/edit
posts. See `src/lib.rs` for code comment annotations.

## Build

```shell
wasm-pack build --target web --release
```

And place the files `pkg/tag_input_wasm_bg.wasm`, `pkg/tag_input_wasm.js` in
the static files directory.

## Usage

Loading and setup of module:

```html
  <script>
      var error = null;
      import("{% static 'tag_input_wasm.js' %}")
          .then((module) => {
          async function run() {
              let w = await module.default("{% static 'tag_input_wasm_bg.wasm' %}");
              //module.setup({singular_name}, {field_name_attribute}, {field_id_attribute}, {json_id_attribute});
              module.setup("tag", "tags", "id_tags", "tags_json");
          }
          return run();
      }).catch(err => {
          console.warn("Could not load tag input .wasm file.\n\nThe error is saved in the global variable `error` for more details. The page and submission form will still work.\n\nYou can use `console.dir(error)` to see what happened.");
          error = err;
      });
  </script>
    {{tags|json_script:"tags_json" }}
```

The `json` `<script>` element should contain a dictionary of valid options as keys and hex colors as values and render as:

```html
<script id="tags_json" type="application/json">{"programming languages": "#ffffff", "python": "#3776ab", }</script>
```

The `<select>` field element should render as:

```html
<select name="tags" id="id_tags" multiple="">
  <option value="19" id="tags-programming languages-option">programming languages</option>
  <option value="21" id="tags-python-option">python</option>
</select>
```

Where `id` is in the format `{field_name_attribute}-{value}-option`.
