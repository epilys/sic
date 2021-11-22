use std::{
    env, str,
    sync::{Arc, Mutex},
};
extern crate readability;
use poptea::{GeminiClient, NoTrustStore};
use readability::extractor;

fn get_http(url: &str) -> Result<String, Box<dyn std::error::Error>> {
    Ok(extractor::scrape(url)?.text)
}

fn get_gemini(url: &str) -> Result<String, Box<dyn std::error::Error>> {
    let gemini_response = poptea::TlsClient::new(Arc::new(Mutex::new(NoTrustStore::default())))
        .get(url)
        .map_err(|e| e.to_string())?;
    Ok(gemini_response
        .body
        .map(String::from_utf8)
        .ok_or("no content")?
        .map_err(|e| e.to_string())?)
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let url = env::args()
        .nth(1)
        .ok_or_else(|| "a single argument is required")?;

    let archive_text = match url.split_once("://").ok_or_else(|| "scheme not provided")? {
        ("https" | "http", _) => get_http(&url)?,
        ("gemini", _) => get_gemini(&url)?,
        _ => return Err("unsuported protocol".into()),
    };

    println!("{}", archive_text.trim());

    Ok(())
}
