use std::env;
use std::io;
extern crate readability;
use readability::extractor;

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let url = env::args().nth(1).ok_or_else(|| {
        Box::new(io::Error::new(
            io::ErrorKind::Other,
            "a single argument is required",
        ))
    })?;
    let product = extractor::scrape(&url)?;
    println!("{}", product.text);
    Ok(())
}
