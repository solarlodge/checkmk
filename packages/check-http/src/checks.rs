// Copyright (C) 2023 Checkmk GmbH - License: GNU General Public License v2
// This file is part of Checkmk (https://checkmk.com). It is subject to the terms and
// conditions defined in the file COPYING, which is part of this source code package.

use httpdate::parse_http_date;
use regex::Regex;
use reqwest::{
    header::{HeaderMap, HeaderValue},
    tls::TlsInfo,
    StatusCode, Version,
};
use std::time::{Duration, SystemTime};
use x509_parser::{certificate::X509Certificate, prelude::FromDer};

use crate::checking_types::{
    check_lower_levels, check_upper_levels, notice, Bounds, CheckResult, LowerLevels, State,
    UpperLevels,
};
use crate::http::{Body, OnRedirect, ProcessedResponse};

pub struct CheckParameters {
    pub onredirect: OnRedirect,
    pub status_code: Vec<StatusCode>,
    pub page_size: Option<Bounds<usize>>,
    pub response_time_levels: Option<UpperLevels<f64>>,
    pub document_age_levels: Option<UpperLevels<u64>>,
    pub timeout: Duration,
    pub body_matchers: Vec<TextMatcher>,
    pub header_matchers: Vec<(TextMatcher, TextMatcher)>,
    pub certificate_levels: Option<LowerLevels<u64>>,
}

pub enum TextMatcher {
    Plain(String),
    Regex { regex: Regex, expectation: bool },
}

impl TextMatcher {
    pub fn match_on(&self, text: &str) -> bool {
        match self {
            Self::Plain(string) => text.contains(string),
            Self::Regex {
                regex,
                expectation: expect_match,
            } => &regex.is_match(text) == expect_match,
        }
    }
}

impl From<String> for TextMatcher {
    fn from(value: String) -> Self {
        Self::Plain(value)
    }
}

impl TextMatcher {
    pub fn from_regex(regex: Regex, expectation: bool) -> Self {
        Self::Regex { regex, expectation }
    }
}

pub fn collect_response_checks(
    response: Result<(ProcessedResponse, Duration), reqwest::Error>,
    params: CheckParameters,
) -> Vec<CheckResult> {
    let (response, response_time) = match response {
        Ok(resp) => resp,
        Err(err) => return check_reqwest_error(err),
    };

    check_status(response.status, response.version, params.status_code)
        .into_iter()
        .chain(check_redirect(response.status, params.onredirect))
        .chain(check_headers(&response.headers, params.header_matchers))
        .chain(check_body(
            response.body,
            params.page_size,
            params.body_matchers,
        ))
        .chain(check_response_time(
            response_time,
            params.response_time_levels,
            params.timeout,
        ))
        .chain(check_document_age(
            SystemTime::now(),
            response
                .headers
                .get("last-modified")
                .or(response.headers.get("date")),
            params.document_age_levels,
        ))
        .chain(check_certificate(
            response.tls_info,
            params.certificate_levels,
        ))
        .flatten()
        .collect()
}

fn check_reqwest_error(err: reqwest::Error) -> Vec<CheckResult> {
    if err.is_timeout() {
        notice(State::Crit, "timeout")
    } else if err.is_connect()
        // Hit one of max_redirs, sticky, stickyport
        | err.is_redirect()
    {
        notice(State::Crit, &err.to_string().replace('\n', " - "))
    } else {
        // The errors coming from reqwest are usually short and don't contain
        // newlines, but we want to be safe.
        notice(State::Unknown, &err.to_string().replace('\n', " - "))
    }
    .into_iter()
    .flatten()
    .collect()
}

fn check_status(
    status: StatusCode,
    version: Version,
    accepted_statuses: Vec<StatusCode>,
) -> Vec<Option<CheckResult>> {
    fn default_statuscode_state(status: StatusCode) -> State {
        if status.is_client_error() {
            State::Warn
        } else if status.is_server_error() {
            State::Crit
        } else {
            State::Ok
        }
    }

    let (state, status_text) = if accepted_statuses.is_empty() {
        (default_statuscode_state(status), String::new())
    } else if accepted_statuses.contains(&status) {
        (State::Ok, String::new())
    } else {
        (
            State::Crit,
            if accepted_statuses.len() == 1 {
                format!(" (expected {})", accepted_statuses[0])
            } else {
                format!(
                    " (expected one of [{}])",
                    accepted_statuses
                        .iter()
                        .map(|st| st.as_u16().to_string())
                        .collect::<Vec<_>>()
                        .join(" ")
                )
            },
        )
    };

    let text = format!("{:?} {}{}", version, status, status_text);
    vec![
        CheckResult::summary(state.clone(), &text),
        CheckResult::details(state, &text),
    ]
}

fn check_redirect(status: StatusCode, onredirect: OnRedirect) -> Vec<Option<CheckResult>> {
    match (status.is_redirection(), onredirect) {
        (true, OnRedirect::Warning) => notice(State::Warn, "Detected redirect"),
        (true, OnRedirect::Critical) => notice(State::Crit, "Detected redirect"),
        _ => vec![],
    }
}

fn check_headers(
    headers: &HeaderMap,
    matchers: Vec<(TextMatcher, TextMatcher)>,
) -> Vec<Option<CheckResult>> {
    if matchers.is_empty() {
        return vec![];
    };

    if match_on_headers(headers, &matchers) {
        vec![]
    } else {
        notice(
            State::Crit,
            "Specified strings not found in response headers",
        )
    }
}

fn match_on_headers(headers: &HeaderMap, matchers: &[(TextMatcher, TextMatcher)]) -> bool {
    let headers_as_strings: Vec<(&str, String)> = headers
        .iter()
        // The header name (coming from reqwest) is guaranteed to be ASCII, so we can have it as string.
        // The header value is only bytes in general. However, RFC 9110, section 5.5 tells us that it
        // should be ASCII and is allowed to be ISO-8859-1 (latin-1), so we decode it with latin-1.
        .map(|(hk, hv)| (hk.as_str(), latin1_to_string(hv.as_bytes())))
        .collect();

    matchers.iter().all(|(key_matcher, value_matcher)| {
        headers_as_strings.iter().any(|(header_key, header_value)| {
            key_matcher.match_on(header_key) && value_matcher.match_on(header_value)
        })
    })
}

fn latin1_to_string(bytes: &[u8]) -> String {
    // latin-1 basically consists of the first two unicode blocks,
    // so it's straighyforward to interpret the u8 values as unicode values.
    bytes.iter().map(|&b| b as char).collect()
}

fn check_body<T: std::error::Error>(
    body: Option<Result<Body, T>>,
    page_size_limits: Option<Bounds<usize>>,
    body_matchers: Vec<TextMatcher>,
) -> Vec<Option<CheckResult>> {
    let Some(body) = body else {
        // We assume that a None-Body means that we didn't fetch it at all
        // and we don't want to perform checks on it.
        return vec![];
    };

    let Ok(body) = body else {
        return notice(State::Crit, "Error fetching the response body");
    };

    check_page_size(body.length, page_size_limits)
        .into_iter()
        .chain(check_body_matching(&body.text, body_matchers))
        .collect()
}

fn check_body_matching(body_text: &str, matcher: Vec<TextMatcher>) -> Vec<Option<CheckResult>> {
    if matcher.iter().any(|m| !m.match_on(body_text)) {
        notice(State::Warn, "String validation failed on response body")
    } else {
        vec![]
    }
}

fn check_page_size(
    page_size: usize,
    page_size_limits: Option<Bounds<usize>>,
) -> Vec<Option<CheckResult>> {
    let state = page_size_limits
        .as_ref()
        .and_then(|bounds| bounds.evaluate(&page_size, State::Warn))
        .unwrap_or(State::Ok);

    let bounds_info = if let State::Warn = state {
        match page_size_limits {
            Some(Bounds { lower, upper: None }) => format!(" (warn below {} Bytes)", lower),
            Some(Bounds {
                lower,
                upper: Some(upper),
            }) => format!(" (warn below/above {} Bytes/{} Bytes)", lower, upper),
            _ => "".to_string(),
        }
    } else {
        "".to_string()
    };

    let mut res = notice(
        state,
        &format!("Page size: {} Bytes{}", page_size, bounds_info),
    );
    res.push(CheckResult::metric(
        "size",
        page_size as f64,
        Some('B'),
        None,
        Some(0.),
        None,
    ));
    res
}

fn check_response_time(
    response_time: Duration,
    response_time_levels: Option<UpperLevels<f64>>,
    timeout: Duration,
) -> Vec<Option<CheckResult>> {
    let mut ret = check_upper_levels(
        "Response time",
        response_time.as_secs_f64(),
        Some(" seconds"),
        &response_time_levels,
    );
    ret.push(CheckResult::metric(
        "time",
        response_time.as_secs_f64(),
        Some('s'),
        response_time_levels,
        Some(0.),
        Some(timeout.as_secs_f64()),
    ));
    ret
}

fn check_document_age(
    now: SystemTime,
    age_header: Option<&HeaderValue>,
    document_age_levels: Option<UpperLevels<u64>>,
) -> Vec<Option<CheckResult>> {
    if document_age_levels.is_none() {
        return vec![];
    };

    let Some(age) = age_header else {
        return notice(State::Crit, "Can't determine document age");
    };
    let document_age_error = "Can't decode document age";
    let Ok(age) = age.to_str() else {
        return notice(State::Crit, document_age_error);
    };
    let Ok(age) = parse_http_date(age) else {
        return notice(State::Crit, document_age_error);
    };
    let Ok(age) = now.duration_since(age) else {
        return notice(State::Crit, document_age_error);
    };

    check_upper_levels(
        "Document age",
        age.as_secs(),
        Some(" seconds"),
        &document_age_levels,
    )
}

// TODO(au): Tests
fn check_certificate(
    tls_info: Option<TlsInfo>,
    certificate_levels: Option<LowerLevels<u64>>,
) -> Vec<Option<CheckResult>> {
    let Some(cert) = tls_info.as_ref().and_then(|t| t.peer_certificate()) else {
        // If the outer tlsinfo is None, we didn't fetch it -> OK
        // If the inner peer cert is None, there is no certificate and we're talking plain HTTP.
        // Otherwise the TLS handshake would already have failed.
        return vec![];
    };

    let Ok((_, cert)) = X509Certificate::from_der(cert) else {
        return notice(State::Unknown, "Unable to parse server certificate");
    };
    let Some(validity) = cert.validity().time_to_expiration() else {
        return notice(State::Crit, "Invalid server certificate");
    };

    check_lower_levels(
        "Server certificate validity",
        validity.whole_days().max(0).unsigned_abs(),
        Some(" days"),
        &certificate_levels,
    )
}

#[cfg(test)]
mod test_check_status {
    use std::vec;

    use super::*;
    use reqwest::{StatusCode, Version};

    #[test]
    fn test_success_unchecked() {
        assert!(
            check_status(StatusCode::OK, Version::HTTP_11, vec![])
                == vec![
                    CheckResult::summary(State::Ok, "HTTP/1.1 200 OK"),
                    CheckResult::details(State::Ok, "HTTP/1.1 200 OK"),
                ]
        )
    }

    #[test]
    fn test_client_error_unchecked() {
        assert!(
            check_status(StatusCode::EXPECTATION_FAILED, Version::HTTP_11, vec![])
                == vec![
                    CheckResult::summary(State::Warn, "HTTP/1.1 417 Expectation Failed"),
                    CheckResult::details(State::Warn, "HTTP/1.1 417 Expectation Failed"),
                ]
        )
    }

    #[test]
    fn test_server_error_unchecked() {
        assert!(
            check_status(StatusCode::INTERNAL_SERVER_ERROR, Version::HTTP_11, vec![])
                == vec![
                    CheckResult::summary(State::Crit, "HTTP/1.1 500 Internal Server Error"),
                    CheckResult::details(State::Crit, "HTTP/1.1 500 Internal Server Error"),
                ]
        )
    }

    #[test]
    fn test_success_checked_ok() {
        assert!(
            check_status(StatusCode::OK, Version::HTTP_11, vec![StatusCode::OK])
                == vec![
                    CheckResult::summary(State::Ok, "HTTP/1.1 200 OK"),
                    CheckResult::details(State::Ok, "HTTP/1.1 200 OK"),
                ]
        )
    }

    #[test]
    fn test_success_checked_not_ok() {
        assert!(
            check_status(StatusCode::OK, Version::HTTP_11, vec![StatusCode::IM_USED])
                == vec![
                    CheckResult::summary(State::Crit, "HTTP/1.1 200 OK (expected 226 IM Used)"),
                    CheckResult::details(State::Crit, "HTTP/1.1 200 OK (expected 226 IM Used)"),
                ]
        )
    }

    #[test]
    fn test_success_checked_multiple_not_ok() {
        assert!(
            check_status(
                StatusCode::OK,
                Version::HTTP_11,
                vec![StatusCode::ACCEPTED, StatusCode::IM_USED]
            ) == vec![
                CheckResult::summary(State::Crit, "HTTP/1.1 200 OK (expected one of [202 226])"),
                CheckResult::details(State::Crit, "HTTP/1.1 200 OK (expected one of [202 226])"),
            ]
        )
    }

    #[test]
    fn test_client_error_checked_ok() {
        assert!(
            check_status(
                StatusCode::IM_A_TEAPOT,
                Version::HTTP_11,
                vec![StatusCode::IM_A_TEAPOT]
            ) == vec![
                CheckResult::summary(State::Ok, "HTTP/1.1 418 I'm a teapot"),
                CheckResult::details(State::Ok, "HTTP/1.1 418 I'm a teapot"),
            ]
        )
    }
}

#[cfg(test)]
mod test_check_redirect {
    use super::*;
    use reqwest::StatusCode;

    #[test]
    fn test_no_redirect() {
        assert!(check_redirect(StatusCode::OK, OnRedirect::Critical) == vec![]);
    }

    #[test]
    fn test_redirect_ok() {
        assert!(check_redirect(StatusCode::MOVED_PERMANENTLY, OnRedirect::Ok) == vec![]);
    }

    #[test]
    fn test_redirect_warn() {
        assert!(
            check_redirect(StatusCode::MOVED_PERMANENTLY, OnRedirect::Warning)
                == vec![
                    CheckResult::summary(State::Warn, "Detected redirect"),
                    CheckResult::details(State::Warn, "Detected redirect"),
                ]
        );
    }

    #[test]
    fn test_redirect_crit() {
        assert!(
            check_redirect(StatusCode::MOVED_PERMANENTLY, OnRedirect::Critical)
                == vec![
                    CheckResult::summary(State::Crit, "Detected redirect"),
                    CheckResult::details(State::Crit, "Detected redirect"),
                ]
        );
    }

    #[test]
    fn test_redirect_not_handled() {
        // This can happen when hitting "max_redirs", but is handled by check_reqwest_error
        assert!(check_redirect(StatusCode::MOVED_PERMANENTLY, OnRedirect::Follow) == vec![]);
    }
}

#[cfg(test)]
mod test_check_headers {
    use reqwest::header::HeaderName;

    use super::*;
    use std::collections::HashMap;
    use std::str::FromStr;

    #[test]
    fn test_no_search_strings() {
        assert!(
            check_headers(
                &(&HashMap::from([
                    ("key1".to_string(), "value1".to_string()),
                    ("key2".to_string(), "value2".to_string()),
                ]))
                    .try_into()
                    .unwrap(),
                vec![]
            ) == vec![]
        )
    }

    #[test]
    fn test_strings_found() {
        assert!(
            check_headers(
                &(&HashMap::from([
                    ("some_key1".to_string(), "some_value1".to_string()),
                    ("some_key2".to_string(), "some_value2".to_string()),
                    ("some_key3".to_string(), "some_value3".to_string()),
                ]))
                    .try_into()
                    .unwrap(),
                vec![
                    (
                        ("some_key1".to_string().into()),
                        "value1".to_string().into()
                    ),
                    (String::new().into(), "value".to_string().into()),
                    ("some_key3".to_string().into(), String::new().into()),
                ]
            ) == vec![]
        )
    }

    #[test]
    fn test_strings_not_found() {
        assert!(
            check_headers(
                &(&HashMap::from([
                    ("some_key1".to_string(), "some_value1".to_string()),
                    ("some_key2".to_string(), "some_value2".to_string()),
                    ("some_key3".to_string(), "some_value3".to_string()),
                ]))
                    .try_into()
                    .unwrap(),
                vec![("key1".to_string().into(), "value2".to_string().into()),]
            ) == vec![
                CheckResult::summary(
                    State::Crit,
                    "Specified strings not found in response headers"
                ),
                CheckResult::details(
                    State::Crit,
                    "Specified strings not found in response headers"
                ),
            ]
        )
    }

    #[test]
    fn test_impossible_non_latin1() {
        assert!(
            check_headers(
                &(&HashMap::from([("some_key1".to_string(), "ßome_value1".to_string()),]))
                    .try_into()
                    .unwrap(),
                vec![(
                    "some_key1".to_string().into(),
                    "ßome_value1".to_string().into()
                ),]
            ) == vec![
                CheckResult::summary(
                    State::Crit,
                    "Specified strings not found in response headers"
                ),
                CheckResult::details(
                    State::Crit,
                    "Specified strings not found in response headers"
                ),
            ]
        )
    }

    #[test]
    fn test_decode_latin1() {
        let mut header_map = HeaderMap::new();
        header_map.append(
            HeaderName::from_str("some_key").unwrap(),
            HeaderValue::from_bytes(b"\xF6\xE4\xFC").unwrap(),
        );
        assert!(
            check_headers(
                &header_map,
                vec![("some_key".to_string().into(), "öäü".to_string().into()),]
            ) == vec![]
        )
    }
}

#[cfg(test)]
mod test_check_body {
    use super::*;
    use std::error::Error;
    use std::fmt::{Display, Formatter, Result};

    #[derive(Debug)]
    struct DummyError;

    impl Error for DummyError {}

    impl Display for DummyError {
        fn fmt(&self, f: &mut Formatter) -> Result {
            write!(f, "Error")
        }
    }

    #[test]
    fn test_no_body() {
        assert!(check_body::<DummyError>(None, None, vec![],) == vec![])
    }

    #[test]
    fn test_error_body() {
        assert!(
            check_body(Some(Err(DummyError {})), None, vec![])
                == vec![
                    CheckResult::summary(State::Crit, "Error fetching the response body"),
                    CheckResult::details(State::Crit, "Error fetching the response body"),
                ]
        );
    }

    #[test]
    fn test_all_ok() {
        assert!(
            check_body::<DummyError>(
                Some(Ok(Body {
                    text: "foobär".to_string(),
                    length: 7
                })),
                Some(Bounds::lower_upper(3, 10)),
                vec!["foo".to_string().into()],
            ) == vec![
                CheckResult::details(State::Ok, "Page size: 7 Bytes"),
                CheckResult::metric("size", 7., Some('B'), None, Some(0.), None)
            ]
        );
    }
}

#[cfg(test)]
mod test_check_page_size {
    use super::*;

    #[test]
    fn test_size_lower_out_of_bounds() {
        assert!(
            check_page_size(42, Some(Bounds::lower(56)),)
                == vec![
                    CheckResult::summary(State::Warn, "Page size: 42 Bytes (warn below 56 Bytes)"),
                    CheckResult::details(State::Warn, "Page size: 42 Bytes (warn below 56 Bytes)"),
                    CheckResult::metric("size", 42., Some('B'), None, Some(0.), None)
                ]
        );
    }

    #[test]
    fn test_size_lower_and_higher_too_low() {
        assert!(
            check_page_size(42, Some(Bounds::lower_upper(56, 100)),)
                == vec![
                    CheckResult::summary(
                        State::Warn,
                        "Page size: 42 Bytes (warn below/above 56 Bytes/100 Bytes)"
                    ),
                    CheckResult::details(
                        State::Warn,
                        "Page size: 42 Bytes (warn below/above 56 Bytes/100 Bytes)"
                    ),
                    CheckResult::metric("size", 42., Some('B'), None, Some(0.), None)
                ]
        );
    }

    #[test]
    fn test_size_lower_and_higher_too_high() {
        assert!(
            check_page_size(142, Some(Bounds::lower_upper(56, 100)),)
                == vec![
                    CheckResult::summary(
                        State::Warn,
                        "Page size: 142 Bytes (warn below/above 56 Bytes/100 Bytes)"
                    ),
                    CheckResult::details(
                        State::Warn,
                        "Page size: 142 Bytes (warn below/above 56 Bytes/100 Bytes)"
                    ),
                    CheckResult::metric("size", 142., Some('B'), None, Some(0.), None)
                ]
        );
    }
}

#[cfg(test)]
mod test_check_body_matching {
    use super::*;

    #[test]
    fn test_no_matcher() {
        assert!(check_body_matching("foobar", vec![]) == vec![]);
    }

    #[test]
    fn test_string_ok() {
        assert!(check_body_matching("foobar", vec!["bar".to_string().into()]) == vec![]);
    }

    #[test]
    fn test_string_not_found() {
        assert!(
            check_body_matching("foobär", vec!["bar".to_string().into()])
                == vec![
                    CheckResult::summary(State::Warn, "String validation failed on response body"),
                    CheckResult::details(State::Warn, "String validation failed on response body"),
                ]
        );
    }

    #[test]
    fn test_regex_ok() {
        assert!(
            check_body_matching(
                "foobar",
                vec![TextMatcher::from_regex(Regex::new("f.*r").unwrap(), true)]
            ) == vec![]
        );
    }

    #[test]
    fn test_regex_not_ok() {
        assert!(
            check_body_matching(
                "foobar",
                vec![TextMatcher::from_regex(Regex::new("f.*z").unwrap(), true)]
            ) == vec![
                CheckResult::summary(State::Warn, "String validation failed on response body"),
                CheckResult::details(State::Warn, "String validation failed on response body"),
            ]
        );
    }

    #[test]
    fn test_regex_inverse_ok() {
        assert!(
            check_body_matching(
                "foobar",
                vec![TextMatcher::from_regex(Regex::new("f.*z").unwrap(), false)]
            ) == vec![]
        );
    }

    #[test]
    fn test_multiple_matchers_ok() {
        assert!(
            check_body_matching(
                "foobar",
                vec!["bar".to_string().into(), "foo".to_string().into()]
            ) == vec![]
        );
    }

    #[test]
    fn test_multiple_matchers_not_ok() {
        assert!(
            check_body_matching(
                "foobar",
                vec!["bar".to_string().into(), "baz".to_string().into()]
            ) == vec![
                CheckResult::summary(State::Warn, "String validation failed on response body"),
                CheckResult::details(State::Warn, "String validation failed on response body"),
            ]
        );
    }
}

#[cfg(test)]
mod test_check_response_time {
    use super::*;
    use std::time::Duration;

    #[test]
    fn test_unbounded() {
        assert!(
            check_response_time(Duration::new(5, 0), None, Duration::from_secs(10))
                == vec![
                    CheckResult::details(State::Ok, "Response time: 5 seconds"),
                    CheckResult::metric("time", 5., Some('s'), None, Some(0.), Some(10.))
                ]
        );
    }

    #[test]
    fn test_warn_within_bounds() {
        assert!(
            check_response_time(
                Duration::new(5, 0),
                Some(UpperLevels::warn(6.)),
                Duration::from_secs(10)
            ) == vec![
                CheckResult::details(State::Ok, "Response time: 5 seconds"),
                CheckResult::metric(
                    "time",
                    5.,
                    Some('s'),
                    Some(UpperLevels::warn(6.)),
                    Some(0.),
                    Some(10.)
                )
            ]
        );
    }

    #[test]
    fn test_warn_is_warn() {
        assert!(
            check_response_time(
                Duration::new(5, 0),
                Some(UpperLevels::warn(4.)),
                Duration::from_secs(10)
            ) == vec![
                CheckResult::summary(State::Warn, "Response time: 5 seconds (warn at 4 seconds)"),
                CheckResult::details(State::Warn, "Response time: 5 seconds (warn at 4 seconds)"),
                CheckResult::metric(
                    "time",
                    5.,
                    Some('s'),
                    Some(UpperLevels::warn(4.)),
                    Some(0.),
                    Some(10.)
                )
            ]
        );
    }

    #[test]
    fn test_warncrit_within_bounds() {
        assert!(
            check_response_time(
                Duration::new(5, 0),
                Some(UpperLevels::warn_crit(6., 7.)),
                Duration::from_secs(10)
            ) == vec![
                CheckResult::details(State::Ok, "Response time: 5 seconds"),
                CheckResult::metric(
                    "time",
                    5.,
                    Some('s'),
                    Some(UpperLevels::warn_crit(6., 7.)),
                    Some(0.),
                    Some(10.)
                )
            ]
        );
    }

    #[test]
    fn test_warncrit_is_warn() {
        assert!(
            check_response_time(
                Duration::new(5, 0),
                Some(UpperLevels::warn_crit(4., 6.)),
                Duration::from_secs(10)
            ) == vec![
                CheckResult::summary(
                    State::Warn,
                    "Response time: 5 seconds (warn/crit at 4 seconds/6 seconds)"
                ),
                CheckResult::details(
                    State::Warn,
                    "Response time: 5 seconds (warn/crit at 4 seconds/6 seconds)"
                ),
                CheckResult::metric(
                    "time",
                    5.,
                    Some('s'),
                    Some(UpperLevels::warn_crit(4., 6.)),
                    Some(0.),
                    Some(10.)
                )
            ]
        );
    }

    #[test]
    fn test_warncrit_is_crit() {
        assert!(
            check_response_time(
                Duration::new(5, 0),
                Some(UpperLevels::warn_crit(2., 3.)),
                Duration::from_secs(10)
            ) == vec![
                CheckResult::summary(
                    State::Crit,
                    "Response time: 5 seconds (warn/crit at 2 seconds/3 seconds)"
                ),
                CheckResult::details(
                    State::Crit,
                    "Response time: 5 seconds (warn/crit at 2 seconds/3 seconds)"
                ),
                CheckResult::metric(
                    "time",
                    5.,
                    Some('s'),
                    Some(UpperLevels::warn_crit(2., 3.)),
                    Some(0.),
                    Some(10.)
                )
            ]
        );
    }
}

#[cfg(test)]
mod test_check_document_age {
    use super::*;

    // All fixed timestamps at 00:00 UTC/GMT
    const UNIX_TIME_2023_11_16: u64 = 1700092800;
    const DATE_2023_11_15: &str = "Wed, 15 Nov 2023 00:00:00 GMT";
    const DATE_2023_11_17: &str = "Fri, 17 Nov 2023 00:00:00 GMT";
    const TWELVE_HOURS: u64 = 12 * 60 * 60;
    const THIRTYSIX_HOURS: u64 = 36 * 60 * 60;

    fn system_time(unix_timestamp: u64) -> SystemTime {
        SystemTime::UNIX_EPOCH + Duration::from_secs(unix_timestamp)
    }

    fn header_date(date: &str) -> HeaderValue {
        HeaderValue::from_str(date).unwrap()
    }

    #[test]
    fn test_no_levels() {
        assert!(
            check_document_age(
                system_time(UNIX_TIME_2023_11_16),
                Some(&header_date("We don't care")),
                None,
            ) == vec![]
        );
    }

    #[test]
    fn test_missing_header_value() {
        assert!(
            check_document_age(
                system_time(UNIX_TIME_2023_11_16),
                None,
                Some(UpperLevels::warn(THIRTYSIX_HOURS)),
            ) == vec![
                CheckResult::summary(State::Crit, "Can't determine document age"),
                CheckResult::details(State::Crit, "Can't determine document age")
            ]
        );
    }

    #[test]
    fn test_erroneous_date() {
        assert!(
            check_document_age(
                system_time(UNIX_TIME_2023_11_16),
                Some(&header_date("Something wrong")),
                Some(UpperLevels::warn(THIRTYSIX_HOURS)),
            ) == vec![
                CheckResult::summary(State::Crit, "Can't decode document age"),
                CheckResult::details(State::Crit, "Can't decode document age")
            ]
        );
    }

    #[test]
    fn test_date_in_future() {
        assert!(
            check_document_age(
                system_time(UNIX_TIME_2023_11_16),
                Some(&header_date(DATE_2023_11_17)),
                Some(UpperLevels::warn(THIRTYSIX_HOURS)),
            ) == vec![
                CheckResult::summary(State::Crit, "Can't decode document age"),
                CheckResult::details(State::Crit, "Can't decode document age")
            ]
        );
    }

    #[test]
    fn test_ok() {
        assert!(
            check_document_age(
                system_time(UNIX_TIME_2023_11_16),
                Some(&header_date(DATE_2023_11_15)),
                Some(UpperLevels::warn(THIRTYSIX_HOURS)),
            ) == vec![CheckResult::details(
                State::Ok,
                "Document age: 86400 seconds"
            )]
        );
    }

    #[test]
    fn test_warn() {
        assert!(
            check_document_age(
                system_time(UNIX_TIME_2023_11_16),
                Some(&header_date(DATE_2023_11_15)),
                Some(UpperLevels::warn(TWELVE_HOURS)),
            ) == vec![
                CheckResult::summary(
                    State::Warn,
                    "Document age: 86400 seconds (warn at 43200 seconds)"
                ),
                CheckResult::details(
                    State::Warn,
                    "Document age: 86400 seconds (warn at 43200 seconds)"
                )
            ]
        );
    }
}
