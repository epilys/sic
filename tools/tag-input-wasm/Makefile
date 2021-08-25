all:
	wasm-pack build --target web

release:
	wasm-pack build --target web --release

install: all
	cp -iv pkg/tag_input_wasm_bg.wasm pkg/tag_input_wasm.js ../../sic/static

install-release: release
	cp -iv pkg/tag_input_wasm_bg.wasm pkg/tag_input_wasm.js ../../sic/static
