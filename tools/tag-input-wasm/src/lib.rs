/*
 * Copyright (C) 2021 Manos Pitsidianakis
 *
 * This program is free software: you can redistribute it and/or modify it under the terms of the
 * GNU Affero General Public License as published by the Free Software Foundation, version 3.
 *
 * This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY;
 * without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
 * the GNU Affero General Public License for more details.
 *
 * You should have received a copy of the GNU Affero General Public License along with this
 * program. If not, see <https://www.gnu.org/licenses/>
 */

/*
 * How this thing works:
 *
 *
 * - Keeps a State with currently selected tags and input state
 * - Setups State in setup() by creating elements, setting up callbacks and initializing State
 * - Synchronizes <select> choices with State choices by listening to input events
 * - Updates DOM in State::update_input and State::update_cloud
 */

mod utils;

use std::collections::HashMap;
use std::ops::Deref;
use std::sync::{Arc, Mutex};
use wasm_bindgen::prelude::*;
use wasm_bindgen::JsCast;
use web_sys::{HtmlInputElement, HtmlSelectElement, KeyboardEvent};

// When the `wee_alloc` feature is enabled, use `wee_alloc` as the global
// allocator.
#[cfg(feature = "wee_alloc")]
#[global_allocator]
static ALLOC: wee_alloc::WeeAlloc = wee_alloc::WeeAlloc::INIT;

const TAG_LIST_ID: &str = "tag-wasm-tag-list";
const TAG_CLOUD_ID: &str = "tag-wasm-tag-cloud";
const DATALIST_ID: &str = "tag-wasm-datalist";
const MSG_ID: &str = "tag-wasm-msg";
const INPUT_ID: &str = "tag-wasm-input";
const DATA_CLOSE_ATTR: &str = "data-close";
const OPTION_DATA_NAME_ATTR: &str = "data-option-name";

struct State {
    tags: Vec<String>,
    is_key_released: bool,
    valid_tags_set: Vec<String>,
    current_input: String,
    valid_tags_map: HashMap<String, (u8, u8, u8)>,
    remove_tag_cb: js_sys::Function,
    add_tag_cb: js_sys::Function,
    select_element_id: String,
    tag_list_id: String,
    tag_cloud_id: String,
    input_id: String,
    datalist_id: String,
    msg_id: String,
    singular_name: String,
    use_datalist: bool,
}

macro_rules! document {
    () => {{
        let window = web_sys::window().expect("no global `window` exists");
        let document = window.document().expect("should have a document on window");
        document
    }};
}

impl State {
    fn update_datalist(&mut self) -> std::result::Result<(), JsValue> {
        if !self.use_datalist {
            return Ok(());
        }
        let document = document!();
        let datalist_el = document
            .get_element_by_id(&self.datalist_id)
            .expect("could not find input element");
        let input_el = document
            .get_element_by_id(&self.input_id)
            .expect("could not find input element");
        let input_el = JsCast::unchecked_into::<HtmlInputElement>(input_el);
        let mut value = input_el.value();
        value.make_ascii_lowercase();
        if value.is_empty() || value.trim() == self.current_input.trim() {
            if value.is_empty() {
                datalist_el.set_text_content(None);
            }
            self.current_input = value;
            return Ok(());
        }
        let results = self
            .valid_tags_set
            .iter()
            .filter_map(|t| {
                if t.contains(&value) {
                    Some(t.trim())
                } else {
                    None
                }
            })
            .collect::<Vec<&str>>();
        datalist_el.set_text_content(None);
        for tag in results {
            if !self.tags.iter().any(|t| t == tag) {
                let tag_el = document.create_element("option")?;
                tag_el.set_text_content(Some(tag));
                datalist_el.append_with_node_1(tag_el.as_ref())?;
            }
        }
        self.current_input = value;
        Ok(())
    }

    fn update_input(&mut self) -> std::result::Result<(), JsValue> {
        let document = document!();
        let tag_list_el = document
            .get_element_by_id(&self.tag_list_id)
            .expect("could not find input element");
        let msg_el = document
            .get_element_by_id(&self.msg_id)
            .expect("could not find msg element");
        msg_el.set_text_content(None);
        while let Some(last_el) = tag_list_el.last_element_child() {
            tag_list_el.remove_child(&last_el)?;
        }
        for tag in &self.tags {
            if let Some((r, g, b)) = self.valid_tags_map.get(tag.as_str()) {
                let tag_el = document.create_element("div")?;
                tag_el.set_attribute("class", "tag")?;
                tag_el.set_attribute(
                    "style",
                    &format!("--red: {}; --green:{}; --blue:{};", r, g, b),
                )?;
                let span_el = document.create_element("span")?;
                span_el.set_text_content(Some("✕"));
                span_el.set_attribute("class", "tag-remove")?;
                span_el.set_attribute(DATA_CLOSE_ATTR, &tag)?;
                {
                    let span_el = JsCast::unchecked_ref::<web_sys::HtmlElement>(&span_el);
                    span_el.set_onclick(Some(self.remove_tag_cb.as_ref()));
                    span_el.set_onkeydown(Some(self.remove_tag_cb.as_ref()));
                }
                tag_el.append_child(&span_el)?;
                let span_el = document.create_element("span")?;
                span_el.set_text_content(Some(tag.as_str()));
                span_el.set_attribute("class", "tag-name")?;
                tag_el.append_child(&span_el)?;
                if tag_list_el.deref().child_nodes().length() != 0 {
                    tag_list_el.append_child(&document.create_text_node(" "))?;
                }
                tag_list_el.append_child(&tag_el)?;
            }
        }
        Ok(())
    }

    fn update_cloud(&mut self) -> std::result::Result<(), JsValue> {
        if self.use_datalist {
            return Ok(());
        }
        let document = document!();
        let tag_cloud_el = document
            .get_element_by_id(&self.tag_cloud_id)
            .expect("could not find input element");
        while let Some(last_el) = tag_cloud_el.last_element_child() {
            tag_cloud_el.remove_child(&last_el)?;
        }
        let input_el = document
            .get_element_by_id(&self.input_id)
            .expect("could not find input element");
        let input_el = JsCast::unchecked_into::<HtmlInputElement>(input_el);
        let mut value = input_el.value();
        value.make_ascii_lowercase();
        let results = self
            .valid_tags_set
            .iter()
            .filter_map(|t| {
                if t.contains(&value) {
                    Some(t.trim())
                } else {
                    None
                }
            })
            .collect::<Vec<&str>>();
        for tag in results {
            if !self.tags.contains(&tag.into()) {
                if let Some((r, g, b)) = self.valid_tags_map.get(tag) {
                    let tag_el = document.create_element("div")?;
                    tag_el.set_attribute("class", "tag")?;
                    tag_el.set_attribute(
                        "style",
                        &format!("--red: {}; --green:{}; --blue:{};", r, g, b),
                    )?;
                    let span_el = document.create_element("span")?;
                    span_el.set_text_content(Some(tag));
                    span_el.set_attribute("class", "tag-name")?;
                    {
                        let tag_el = JsCast::unchecked_ref::<web_sys::HtmlElement>(&tag_el);
                        tag_el.set_onclick(Some(self.add_tag_cb.as_ref()));
                        tag_el.set_onkeydown(Some(self.add_tag_cb.as_ref()));
                    }
                    tag_el.append_child(&span_el)?;
                    if tag_cloud_el.deref().child_nodes().length() != 0 {
                        tag_cloud_el.append_child(&document.create_text_node(" "))?;
                    }
                    tag_cloud_el.append_child(&tag_el)?;
                }
            }
        }
        Ok(())
    }

    fn add_tag(&mut self, tag: String) -> std::result::Result<(), JsValue> {
        let document = document!();
        let root_el = document
            .get_element_by_id(&self.select_element_id)
            .expect("could not find tag element");
        let input_el = document
            .get_element_by_id(&self.input_id)
            .expect("could not find input element");
        let input_el = JsCast::unchecked_into::<HtmlInputElement>(input_el);
        let msg_el = document
            .get_element_by_id(&self.msg_id)
            .expect("could not find msg element");
        if !self.valid_tags_set.contains(&tag) {
            msg_el.set_text_content(Some(&format!("{} does not exist.", &self.singular_name)));
        } else if !self.tags.contains(&tag) {
            if let Some(opt) = root_el
                .query_selector(&format!("[{}=\"{}\"]", OPTION_DATA_NAME_ATTR, tag))
                .ok()
                .and_then(|el| el)
                .and_then(|el| JsCast::dyn_into::<web_sys::HtmlOptionElement>(el).ok())
            {
                opt.set_selected(true);
            }
            self.tags.push(tag);
            input_el.set_value("");
            self.update_cloud()?;
            self.update_input()?;
            self.update_datalist()?;
        }
        Ok(())
    }

    fn pop(&mut self) -> Option<String> {
        if let Some(tag) = self.tags.pop() {
            let document = document!();
            let root_el = document
                .get_element_by_id(&self.select_element_id)
                .expect("could not find tag element");
            let root_el = JsCast::unchecked_into::<HtmlSelectElement>(root_el);
            if let Some(opt) = root_el
                .query_selector(&format!("[{}=\"{}\"]", OPTION_DATA_NAME_ATTR, tag))
                .ok()
                .and_then(|el| el)
                .and_then(|el| JsCast::dyn_into::<web_sys::HtmlOptionElement>(el).ok())
            {
                opt.set_selected(false);
                opt.remove_attribute("selected").unwrap();
            }
            Some(tag)
        } else {
            None
        }
    }

    fn autocomplete(&mut self, value: String) -> Option<String> {
        if value.is_empty() {
            return None;
        }
        let results = self
            .valid_tags_set
            .iter()
            .filter_map(|t| {
                if t.starts_with(&value) {
                    Some(t.trim())
                } else {
                    None
                }
            })
            .collect::<Vec<&str>>();
        if results.len() == 1 {
            let tag = results[0].to_string();
            let document = document!();
            let root_el = document
                .get_element_by_id(&self.select_element_id)
                .expect("could not find tag element");
            let root_el = JsCast::unchecked_into::<HtmlSelectElement>(root_el);
            if let Some(opt) = root_el
                .query_selector(&format!("[{}=\"{}\"]", OPTION_DATA_NAME_ATTR, tag))
                .ok()
                .and_then(|el| el)
                .and_then(|el| JsCast::dyn_into::<web_sys::HtmlOptionElement>(el).ok())
            {
                opt.set_selected(true);
            }
            Some(tag)
        } else {
            None
        }
    }

    fn remove_tag(&mut self, event: web_sys::Event) -> std::result::Result<(), JsValue> {
        let document = document!();
        let root_el = document
            .get_element_by_id(&self.select_element_id)
            .expect("could not find tag element");
        let root_el = JsCast::unchecked_into::<HtmlSelectElement>(root_el);
        if let Some(target) = event.target() {
            let el = JsCast::dyn_into::<web_sys::HtmlSpanElement>(target)?;
            if let Some(tag) = el.get_attribute(DATA_CLOSE_ATTR) {
                if let Some(index) = self.tags.iter().position(|t| t == &tag) {
                    self.tags.remove(index);
                    if let Some(opt) = root_el
                        .query_selector(&format!("[{}=\"{}\"]", OPTION_DATA_NAME_ATTR, tag))
                        .ok()
                        .and_then(|el| el)
                        .and_then(|el| JsCast::dyn_into::<web_sys::HtmlOptionElement>(el).ok())
                    {
                        opt.set_selected(false);
                        opt.remove_attribute("selected").unwrap();
                    }
                    self.update_cloud()?;
                    self.update_input()?;
                }
            }
        }
        Ok(())
    }

    fn update_from_select(&mut self) -> std::result::Result<(), JsValue> {
        let document = document!();
        let root_el = document
            .get_element_by_id(&self.select_element_id)
            .expect("could not find tag element");
        let root_el = JsCast::unchecked_into::<HtmlSelectElement>(root_el);
        let mut selected = vec![];
        for tag in self.valid_tags_set.iter() {
            if let Some(opt) = root_el
                .query_selector(&format!("[{}=\"{}\"]", OPTION_DATA_NAME_ATTR, tag))
                .ok()
                .and_then(|el| el)
                .and_then(|el| JsCast::dyn_into::<web_sys::HtmlOptionElement>(el).ok())
            {
                if opt.selected() {
                    selected.push(tag.to_string());
                }
            }
        }
        if selected != self.tags || selected.is_empty() {
            self.tags = selected;
            self.update_cloud()?;
            self.update_input()?;
        }
        Ok(())
    }
}

fn hex_to_rgb(hex: &str) -> (u8, u8, u8) {
    let mut string = hex.to_string();
    string.make_ascii_lowercase();

    if string.starts_with('#') {
        let string_char_count = string.chars().count();

        if string_char_count == 4 {
            let (_, value_string) = string.split_at(1);

            let iv = match u64::from_str_radix(value_string, 16) {
                Ok(v) => v,
                Err(_) => {
                    return (255, 255, 255);
                }
            };

            if iv > 0xfff {
                return (255, 255, 255);
            }

            return (
                (((iv & 0xf00) >> 4) | ((iv & 0xf00) >> 8)) as u8,
                ((iv & 0xf0) | ((iv & 0xf0) >> 4)) as u8,
                ((iv & 0xf) | ((iv & 0xf) << 4)) as u8,
            );
        } else if string_char_count == 7 {
            let (_, value_string) = string.split_at(1);

            let iv = match u64::from_str_radix(value_string, 16) {
                Ok(v) => v,
                Err(_) => {
                    return (255, 255, 255);
                }
            };

            if iv > 0xffffff {
                return (255, 255, 255);
            }

            return (
                ((iv & 0xff0000) >> 16) as u8,
                ((iv & 0xff00) >> 8) as u8,
                (iv & 0xff) as u8,
            );
        }
    }
    (255, 255, 255)
}

#[wasm_bindgen]
pub fn setup(
    singular_name: String,
    select_element_id: String,
    tags_json_id: String,
    use_datalist: bool,
) -> std::result::Result<(), JsValue> {
    utils::set_panic_hook();
    let tag_list_id = format!("{}-{}", &select_element_id, TAG_LIST_ID);
    let tag_cloud_id = format!("{}-{}", &select_element_id, TAG_CLOUD_ID);
    let input_id = format!("{}-{}", &select_element_id, INPUT_ID);
    let datalist_id = format!("{}-{}", &select_element_id, DATALIST_ID);
    let msg_id = format!("{}-{}", &select_element_id, MSG_ID);
    /* 1. Create elements */
    let document = document!();
    let root_el = document
        .get_element_by_id(&select_element_id)
        .expect("could not find tag element");
    {
        let children = root_el.children();

        for i in 0..(children.length()) {
            if let Some(c) = children.item(i) {
                let text = if let Some(c) = JsCast::dyn_ref::<web_sys::HtmlOptionElement>(&c) {
                    c.text()
                } else {
                    continue;
                };
                c.set_attribute(OPTION_DATA_NAME_ATTR, &text)?;
            }
        }
    }
    let root_help_text_el = root_el.previous_element_sibling().expect("");
    let tag_container = document.create_element("div")?;
    tag_container.set_id(&format!("{}-tag-wasm", &select_element_id));
    tag_container.set_attribute("class", "tag-wasm")?;
    tag_container.set_attribute("aria-hidden", "true")?;
    tag_container.set_inner_html(&format!(r#"<div id="{}"></div>"#, &tag_list_id));
    let tag_cloud_el = document.create_element("div")?;
    tag_cloud_el.set_id(&tag_cloud_id);
    tag_cloud_el.set_attribute("class", &format!("{} {}", TAG_CLOUD_ID, TAG_LIST_ID))?;
    tag_cloud_el.set_attribute("aria-hidden", "true")?;
    let input_el = document.create_element("input")?;
    input_el.set_id(&input_id);
    input_el.set_attribute("class", INPUT_ID)?;
    let input_el = JsCast::unchecked_into::<HtmlInputElement>(input_el);
    input_el.set_attribute("list", &datalist_id)?;
    input_el.set_type("text");
    input_el.set_placeholder(&format!("{} name…", &singular_name));
    tag_container.append_with_node_1(&document.create_text_node(" "))?;
    tag_container.append_with_node_1(input_el.as_ref())?;
    {
        let input_id = input_id.clone();
        let onclick_db = Closure::wrap(Box::new(move |_event: web_sys::Event| {
            JsCast::unchecked_into::<web_sys::HtmlElement>(
                document!().get_element_by_id(&input_id).expect(""),
            )
            .focus()
            .unwrap();
        }) as Box<dyn FnMut(_)>);
        JsCast::unchecked_ref::<web_sys::HtmlElement>(&tag_container)
            .set_onclick(Some(onclick_db.as_ref().unchecked_ref()));
        onclick_db.forget();
    }
    root_help_text_el.before_with_node_1(tag_container.as_ref())?;
    let help_text_el = document.create_element("p")?;
    help_text_el.set_inner_html(&format!("Type {} names, terminated with <kbd>,</kbd>. Press <kbd>Backspace</kbd> repeatedly on empty input to remove last {}.", &singular_name, &singular_name));
    help_text_el.set_attribute("class", "help-text tag-wasm-help-text")?;
    help_text_el.set_attribute("aria-hidden", "true")?;
    tag_container.before_with_node_1(help_text_el.as_ref())?;
    let msg_el = document.create_element("div")?;
    msg_el.set_id(&msg_id);
    msg_el.set_attribute("class", MSG_ID)?;
    msg_el.set_attribute("aria-hidden", "true")?;
    tag_container.after_with_node_1(msg_el.as_ref())?;
    tag_container.after_with_node_1(tag_cloud_el.as_ref())?;
    let after_help_text_el = document.create_element("p")?;
    after_help_text_el.set_text_content(Some("Or, "));
    after_help_text_el.set_attribute("class", "after help-text tag-wasm-help-text")?;
    after_help_text_el.set_attribute("aria-hidden", "true")?;
    msg_el.after_with_node_1(after_help_text_el.as_ref())?;
    let datalist_el = document.create_element("datalist")?;
    datalist_el.set_id(&datalist_id);
    datalist_el.set_attribute("class", DATALIST_ID)?;
    root_el.after_with_node_1(datalist_el.as_ref())?;
    document
        .get_element_by_id(&tag_list_id)
        .expect("could not find input element")
        .set_attribute("class", TAG_LIST_ID)?;

    /* 2. Initialize State object */
    let valid_tags: JsValue = js_sys::JSON::parse(
        &document
            .get_element_by_id(&tags_json_id)
            .expect("could not find tag json data")
            .text_content()
            .unwrap_or_default(),
    )?;

    /* This is a dummy callback for the `remove_tag_cb` field. When the State has been created, we
     * will replace it with the actual callback because it needs a state reference. */
    let dummy_cb = Closure::wrap(Box::new(move |_event: web_sys::Event| {}) as Box<dyn FnMut(_)>);
    let state: Arc<Mutex<State>> = Arc::new(Mutex::new(State {
        tags: vec![],
        is_key_released: false,
        valid_tags_set: js_sys::Object::keys(&js_sys::Object::from(valid_tags.clone()))
            .to_vec()
            .into_iter()
            .filter_map(|jv| jv.as_string())
            .collect::<Vec<String>>(),
        current_input: String::new(),
        valid_tags_map: js_sys::Object::keys(&js_sys::Object::from(valid_tags.clone()))
            .to_vec()
            .into_iter()
            .filter_map(|jv| jv.as_string())
            .zip(
                js_sys::Object::values(&js_sys::Object::from(valid_tags))
                    .to_vec()
                    .into_iter()
                    .filter_map(|jv| jv.as_string())
                    .map(|s| hex_to_rgb(&s)),
            )
            .collect::<HashMap<String, (u8, u8, u8)>>(),
        remove_tag_cb: dummy_cb
            .as_ref()
            .unchecked_ref::<js_sys::Function>()
            .clone(),
        add_tag_cb: dummy_cb
            .as_ref()
            .unchecked_ref::<js_sys::Function>()
            .clone(),
        select_element_id,
        tag_list_id,
        input_id,
        datalist_id,
        msg_id,
        singular_name,
        tag_cloud_id,
        use_datalist,
    }));

    /*
     * 3. Create `{add,remove}_tag_cb` callback. Remove gets called when the little 'x' in a tag element is
     *    clicked or pressed with a key. Add gets called when clicking on a tag in the cloud.
     */
    {
        let state_ = state.clone();
        let state__ = state.clone();
        let cb = Closure::wrap(Box::new(move |event: web_sys::Event| {
            event.prevent_default();
            state_.lock().unwrap().remove_tag(event).unwrap();
        }) as Box<dyn FnMut(_)>);
        state__.lock().unwrap().remove_tag_cb =
            cb.as_ref().unchecked_ref::<js_sys::Function>().clone();
        cb.forget();
    }
    {
        let state_ = state.clone();
        let state__ = state.clone();
        let cb = Closure::wrap(Box::new(move |event: web_sys::Event| {
            event.prevent_default();
            if let Some(el) = event
                .target()
                .and_then(|el| JsCast::dyn_into::<web_sys::HtmlSpanElement>(el).ok())
                .or_else(|| {
                    event
                        .target()
                        .and_then(|el| JsCast::dyn_into::<web_sys::HtmlElement>(el).ok())
                        .and_then(|el| el.first_element_child())
                        .and_then(|el| JsCast::dyn_into::<web_sys::HtmlSpanElement>(el).ok())
                })
            {
                state_.lock().unwrap().add_tag(el.inner_text()).unwrap();
            }
        }) as Box<dyn FnMut(_)>);
        state__.lock().unwrap().add_tag_cb =
            cb.as_ref().unchecked_ref::<js_sys::Function>().clone();
        cb.forget();
    }
    /*
     * 4. Create an oninput callback for the <select> element, so that we synchronise its state
     *    with our State.
     */
    {
        let state = state.clone();
        let cb = Closure::wrap(Box::new(move |_event: web_sys::Event| {
            state.lock().unwrap().update_from_select().unwrap();
        }) as Box<dyn FnMut(_)>);
        let root_el = JsCast::unchecked_into::<web_sys::HtmlElement>(root_el);
        root_el.set_oninput(Some(cb.as_ref().unchecked_ref()));
        cb.forget();
    }
    /*
     * 5. Create an onkeydown callback that checks every key press for
     *
     *  - a comma character ',' which is used as a separator. Current input is inserted as a tag if
     *    it's valid.
     *  - Backspace. If pressed repeatedly and input field is empty, remove the last tag and put it
     *    in the input field.
     *
     *  The "repeatedly" part is tracked with the 'is_key_released` boolean flag and set to true on
     *  the next callback.
     */
    {
        let state = state.clone();
        let cb = Closure::wrap(Box::new(move |event: web_sys::Event| {
            let mut state_lck = state.lock().unwrap();
            let tag_list_el = document
                .get_element_by_id(&state_lck.tag_list_id)
                .expect("could not find input element");
            let input_el = document
                .get_element_by_id(&state_lck.input_id)
                .expect("could not find input element");
            let input_el = JsCast::unchecked_into::<HtmlInputElement>(input_el);
            if let Ok(event) = JsCast::dyn_into::<KeyboardEvent>(event) {
                let value = input_el.value();
                if (event.key() == "," || event.key() == "Enter") && !value.is_empty() {
                    event.prevent_default();
                    state_lck.add_tag(value.trim().to_string()).unwrap();
                } else if event.key() == "Tab" {
                    event.prevent_default();
                    if let Some(tag) = state_lck.autocomplete(value) {
                        input_el.set_value(tag.as_str());
                        state_lck.add_tag(tag).unwrap();
                        state_lck.update_cloud().unwrap();
                        state_lck.update_input().unwrap();
                    }
                } else if event.key() == "Backspace"
                    && value.is_empty()
                    && tag_list_el.child_element_count() != 0
                    && state_lck.is_key_released
                {
                    event.prevent_default();
                    if let Some(tag) = state_lck.pop() {
                        input_el.set_value(tag.as_str());
                        state_lck.update_cloud().unwrap();
                        state_lck.update_input().unwrap();
                    }
                }
            }
            state_lck.is_key_released = false;
        }) as Box<dyn FnMut(_)>);
        input_el.set_onkeydown(Some(cb.as_ref().unchecked_ref()));
        cb.forget();
    }

    /*
     * 6. Create the `is_key_released` onkeyup callback.
     */
    {
        let state = state.clone();
        let cb = Closure::wrap(Box::new(move |_event: web_sys::Event| {
            let mut state_lck = state.lock().unwrap();
            state_lck.is_key_released = true;
            state_lck.update_cloud().unwrap();
            state_lck.update_datalist().unwrap();
        }) as Box<dyn FnMut(_)>);
        input_el.set_onkeyup(Some(cb.as_ref().unchecked_ref()));
        cb.forget();
    }

    /*
     * 7. Update state if form was created with initial data
     */
    state.lock().unwrap().update_from_select()?;

    /*
     * 8. Finally, forget the state copy so that it exists as long as the page lives. Not
     *    necessary but good to know it sticks around.
     */
    std::mem::forget(state);

    Ok(())
}
