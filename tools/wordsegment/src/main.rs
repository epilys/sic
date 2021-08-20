use instant_segment::{Search, Segmenter};
use std::collections::HashMap;
use std::fs::File;
use std::io::prelude::*;
use std::path::Path;

use std::io::{self, BufRead};
use regex::Regex;

fn seg_to_asciis(s: String) -> Vec<(bool, String)> {
    let mut ret = vec![];
    let mut is_ascii = true;
    let mut acc = String::new();
    for c in s.chars() {
        if c == '\u{c}' {
            continue;
        }

        if c == 'ﬁ' {
            if !is_ascii {
                ret.push((is_ascii, std::mem::replace(&mut acc, String::new())));
                is_ascii = true;
            }
            acc.push('f');
            acc.push('i');
            continue;
        }
        if c == 'ﬂ' {
            if !is_ascii {
                ret.push((is_ascii, std::mem::replace(&mut acc, String::new())));
                is_ascii = true;
            }
            acc.push('f');
            acc.push('l');
            continue;
        }
        if c.is_ascii_alphabetic() {
            if !is_ascii {
                ret.push((is_ascii, std::mem::replace(&mut acc, String::new())));
                is_ascii = true;
            }
                acc.push(c);
        } else {
            if is_ascii {
                ret.push((is_ascii, std::mem::replace(&mut acc, String::new())));
                is_ascii = false;
            }
            acc.push(c);
        }
    }
    ret
}

fn main() -> io::Result<()> {
    let re = Regex::new(r"(?P<a>[a-zA-Z])-(?P<b>[a-zA-Z])").unwrap();
    let mut buffer = String::new();
    let input = io::stdin().read_to_string(&mut buffer)?;
    let buffer = re.replace_all(&buffer, "$a$b").to_string();
    //println!("{:?}", seg_to_asciis(buffer.clone()));
    //println!(" buffer = {:?}", &buffer);
    let mut unigrams = HashMap::default();
    for line in read_lines("unigrams.txt")? {
        let line = line.unwrap();
        let mut parts = line.split_whitespace();
        unigrams.insert(
            parts.next().unwrap().into(),
            parts.next().unwrap().parse::<f64>().unwrap(),
        );
    }

    let mut bigrams = HashMap::default();
    for line in read_lines("bigrams.txt")? {
        let line = line.unwrap();
        let mut parts = line.split_whitespace();
        bigrams.insert(
            (parts.next().unwrap().into(), parts.next().unwrap().into()),
            parts.next().unwrap().parse::<f64>().unwrap(),
        );
    }

    let segmenter = Segmenter::from_maps(unigrams, bigrams);
    let mut words = vec![];
    println!("{:?}\n\n", seg_to_asciis(buffer.clone()));
    for (is_ascii, mut seg) in seg_to_asciis(buffer) {
    let mut search = Search::default();
        if !is_ascii {
            words.push(seg);
        } else {
            seg.make_ascii_lowercase();
            match segmenter.segment(&seg, &mut search) {
                Ok(mut iter) => {
                    for word in iter {
                        words.push(word.to_string());
                    }
                }
                Err(err) => {
                    eprintln!("err with seg {:?} {}", &seg, err);

                    words.push(seg);
                }
            }
        }
    }

    let mut output = words.join(" ");
    let mut output = Regex::new(r#"\s*\(\s*"#).unwrap().replace_all(&output, " (");
    let mut output = Regex::new(r#"\s*\)\s*"#).unwrap().replace_all(&output, ") ");
    let mut output = Regex::new(r#"\s*(?P<p>[.,!"'’;:?])\s*"#).unwrap().replace_all(&output, "$p ");
    println!("{}", output);
    Ok(())
}

// The output is wrapped in a Result to allow matching on errors
// Returns an Iterator to the Reader of the lines of the file.
fn read_lines<P>(filename: P) -> io::Result<io::Lines<io::BufReader<File>>>
where
    P: AsRef<Path>,
{
    let file = File::open(filename)?;
    Ok(io::BufReader::new(file).lines())
}
