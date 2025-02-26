// Copyright (C) 2023 Checkmk GmbH - License: GNU General Public License v2
// This file is part of Checkmk (https://checkmk.com). It is subject to the terms and
// conditions defined in the file COPYING, which is part of this source code package.

use super::defines::{defaults, keys, values};
use super::section::{Section, SectionKind, Sections};
use super::yaml::{Get, Yaml};
use crate::types::{HostName, InstanceAlias, InstanceName, MaxConnections, MaxQueries, Port};
use anyhow::{anyhow, bail, Context, Result};
use std::collections::hash_map::DefaultHasher;
use std::hash::{Hash, Hasher};
use std::path::{Path, PathBuf};
use std::time::Duration;
use yaml_rust::YamlLoader;

#[derive(PartialEq, Debug)]
pub struct Config {
    auth: Authentication,
    conn: Connection,
    sections: Sections,
    discovery: Discovery,
    piggyback_host: Option<String>,
    mode: Mode,
    custom_instances: Vec<CustomInstance>,
    configs: Vec<Config>,
    hash: String,
    options: Options,
}

#[derive(PartialEq, Debug, Clone)]
pub struct Options {
    max_connections: MaxConnections,
    max_queries: MaxQueries,
}

impl Default for Options {
    fn default() -> Self {
        Self {
            max_connections: defaults::MAX_CONNECTIONS.into(),
            max_queries: defaults::MAX_QUERIES.into(),
        }
    }
}

impl Options {
    pub fn new(max_connections: MaxConnections) -> Self {
        Self {
            max_connections,
            max_queries: defaults::MAX_QUERIES.into(),
        }
    }

    pub fn max_connections(&self) -> MaxConnections {
        self.max_connections.clone()
    }

    pub fn max_queries(&self) -> MaxQueries {
        self.max_queries.clone()
    }

    pub fn from_yaml(yaml: &Yaml) -> Result<Option<Self>> {
        let options = yaml.get(keys::OPTIONS);
        if options.is_badvalue() {
            return Ok(None);
        }

        Ok(Some(Self {
            max_connections: options
                .get_int::<u32>(keys::MAX_CONNECTIONS)
                .unwrap_or_else(|| {
                    log::debug!("no max_connections specified, using default");
                    defaults::MAX_CONNECTIONS
                })
                .into(),
            max_queries: defaults::MAX_QUERIES.into(),
        }))
    }
}

impl Default for Config {
    fn default() -> Self {
        Self {
            auth: Authentication::default(),
            conn: Connection::default(),
            sections: Sections::default(),
            discovery: Discovery::default(),
            piggyback_host: None,
            mode: Mode::Port,
            custom_instances: vec![],
            configs: vec![],
            hash: String::new(),
            options: Options::default(),
        }
    }
}

impl Config {
    pub fn from_string(source: &str) -> Result<Option<Self>> {
        YamlLoader::load_from_str(source)?
            .get(0)
            .and_then(|e| Config::from_yaml(e).transpose())
            .transpose()
    }

    pub fn from_yaml(yaml: &Yaml) -> Result<Option<Self>> {
        let root = yaml.get(keys::MSSQL);
        if root.is_badvalue() {
            return Ok(None);
        }
        let default_config = Config {
            auth: Authentication {
                auth_type: AuthType::Undefined,
                ..Default::default()
            },
            ..Default::default()
        };
        let config = Config::parse_main_from_yaml(root, &default_config)?;
        match config {
            Some(c) if !c.auth.defined() => {
                anyhow::bail!("Bad/absent user name");
            }
            Some(mut c) => {
                c.configs = root
                    .get_yaml_vector(keys::CONFIGS)
                    .into_iter()
                    .filter_map(|v| Config::parse_main_from_yaml(&v, &c).transpose())
                    .collect::<Result<Vec<Config>>>()?;

                Ok(Some(c))
            }
            _ => Ok(config),
        }
    }

    fn parse_main_from_yaml(root: &Yaml, default: &Config) -> Result<Option<Self>> {
        let mut hasher = DefaultHasher::new();
        root.hash(&mut hasher);
        let hash = format!("{:016X}", hasher.finish());
        let main = root.get(keys::MAIN);
        if main.is_badvalue() {
            bail!("main key is absent");
        }

        let auth = Authentication::from_yaml(main).unwrap_or_else(|_| default.auth.clone());
        let conn =
            Connection::from_yaml(main, Some(&auth))?.unwrap_or_else(|| default.conn().clone());
        let options = Options::from_yaml(main)?.unwrap_or_else(|| default.options().clone());
        let discovery = Discovery::from_yaml(main)?.unwrap_or_else(|| default.discovery().clone());
        let section_info = Sections::from_yaml(main, &default.sections)?;

        let custom_instances = main
            .get_yaml_vector(keys::INSTANCES)
            .into_iter()
            .map(|v| CustomInstance::from_yaml(&v, &auth, &conn, &section_info))
            .collect::<Result<Vec<CustomInstance>>>()?;
        let mode = Mode::from_yaml(main).unwrap_or_else(|_| default.mode().clone());
        let piggyback_host = main.get_string(keys::PIGGYBACK_HOST);

        Ok(Some(Self {
            auth,
            conn,
            sections: section_info,
            discovery,
            piggyback_host,
            mode,
            custom_instances,
            configs: vec![],
            hash,
            options,
        }))
    }

    pub fn options(&self) -> &Options {
        &self.options
    }

    pub fn endpoint(&self) -> Endpoint {
        Endpoint::new(&self.auth, &self.conn)
    }
    pub fn auth(&self) -> &Authentication {
        &self.auth
    }
    pub fn conn(&self) -> &Connection {
        &self.conn
    }
    pub fn all_sections(&self) -> &Vec<Section> {
        self.sections.sections()
    }
    pub fn valid_sections(&self) -> Vec<&Section> {
        self.sections
            .select(&[SectionKind::Sync, SectionKind::Async])
    }

    pub fn cache_age(&self) -> u32 {
        self.sections.cache_age()
    }

    pub fn piggyback_host(&self) -> Option<&str> {
        self.piggyback_host.as_deref()
    }

    pub fn discovery(&self) -> &Discovery {
        &self.discovery
    }
    pub fn mode(&self) -> &Mode {
        &self.mode
    }
    pub fn instances(&self) -> &Vec<CustomInstance> {
        &self.custom_instances
    }
    pub fn configs(&self) -> &Vec<Config> {
        &self.configs
    }

    pub fn hash(&self) -> &str {
        &self.hash
    }

    pub fn cache_dir(&self) -> String {
        "mssql-".to_owned() + &self.hash
    }

    pub fn sections(&self) -> &Sections {
        &self.sections
    }

    pub fn is_instance_allowed(&self, name: &impl ToString) -> bool {
        if !self.discovery.include().is_empty() {
            return self.discovery.include().contains(&name.to_string());
        }

        if self.discovery.exclude().contains(&name.to_string()) {
            return false;
        }

        true
    }
}

#[derive(PartialEq, Debug, Clone)]
pub struct Authentication {
    username: String,
    password: Option<String>,
    auth_type: AuthType,
    access_token: Option<String>,
}

impl Default for Authentication {
    fn default() -> Self {
        Self {
            username: "".to_owned(),
            password: None,
            auth_type: AuthType::default(),
            access_token: None,
        }
    }
}
impl Authentication {
    pub fn from_yaml(yaml: &Yaml) -> Result<Self> {
        let auth = yaml.get(keys::AUTHENTICATION);
        if auth.is_badvalue() {
            anyhow::bail!("authentication is missing");
        }

        Ok(Self {
            username: auth.get_string(keys::USERNAME).unwrap_or_default(),
            password: auth.get_string(keys::PASSWORD),
            auth_type: AuthType::try_from(
                auth.get_string(keys::TYPE)
                    .as_deref()
                    .unwrap_or(defaults::AUTH_TYPE),
            )?,
            access_token: auth.get_string(keys::ACCESS_TOKEN),
        }
        .ensure())
    }
    pub fn username(&self) -> &str {
        &self.username
    }
    pub fn password(&self) -> Option<&String> {
        self.password.as_ref()
    }
    pub fn auth_type(&self) -> &AuthType {
        &self.auth_type
    }
    pub fn access_token(&self) -> Option<&String> {
        self.access_token.as_ref()
    }

    pub fn defined(&self) -> bool {
        self.auth_type() == &AuthType::Integrated || !self.username().is_empty()
    }

    fn ensure(mut self) -> Self {
        if self.auth_type() == &AuthType::Integrated {
            self.username = String::new();
            self.password = None;
            self.access_token = None;
        }
        self
    }
}

#[derive(PartialEq, Debug, Clone)]
pub enum AuthType {
    SqlServer,
    Windows,
    Integrated,
    Token,
    Undefined,
}

impl Default for AuthType {
    #[cfg(unix)]
    fn default() -> Self {
        Self::SqlServer
    }
    #[cfg(windows)]
    fn default() -> Self {
        Self::Integrated
    }
}

impl TryFrom<&str> for AuthType {
    type Error = anyhow::Error;

    fn try_from(val: &str) -> Result<Self> {
        match str::to_ascii_lowercase(val).as_ref() {
            values::SQL_SERVER => Ok(AuthType::SqlServer),
            #[cfg(windows)]
            values::WINDOWS => Ok(AuthType::Windows),
            #[cfg(windows)]
            values::INTEGRATED => Ok(AuthType::Integrated),
            values::TOKEN => Ok(AuthType::Token),
            _ => Err(anyhow!("unsupported auth type `{val}`")),
        }
    }
}

#[derive(PartialEq, Debug, Clone)]
pub struct Connection {
    hostname: HostName,
    fail_over_partner: Option<String>,
    port: Port,
    socket: Option<PathBuf>,
    tls: Option<ConnectionTls>,
    timeout: u64,
}

impl Connection {
    pub fn from_yaml(yaml: &Yaml, auth: Option<&Authentication>) -> Result<Option<Self>> {
        let conn = yaml.get(keys::CONNECTION);
        if conn.is_badvalue() {
            return Ok(None);
        }
        Ok(Some(
            Self {
                hostname: conn
                    .get_string(keys::HOSTNAME)
                    .unwrap_or_else(|| defaults::CONNECTION_HOST_NAME.to_string())
                    .to_lowercase()
                    .into(),
                fail_over_partner: conn.get_string(keys::FAIL_OVER_PARTNER),
                port: Port(conn.get_int::<u16>(keys::PORT).unwrap_or_else(|| {
                    log::debug!("no port specified, using default");
                    defaults::CONNECTION_PORT
                })),
                socket: conn.get_pathbuf(keys::SOCKET),
                tls: ConnectionTls::from_yaml(conn)?,
                timeout: conn.get_int::<u64>(keys::TIMEOUT).unwrap_or_else(|| {
                    log::debug!("no timeout specified, using default");
                    defaults::CONNECTION_TIMEOUT
                }),
            }
            .ensure(auth),
        ))
    }
    pub fn hostname(&self) -> &HostName {
        &self.hostname
    }
    pub fn fail_over_partner(&self) -> Option<&String> {
        self.fail_over_partner.as_ref()
    }
    pub fn port(&self) -> Port {
        self.port.clone()
    }
    pub fn sql_browser_port(&self) -> Option<u16> {
        None
    }
    pub fn socket(&self) -> Option<&PathBuf> {
        self.socket.as_ref()
    }
    pub fn tls(&self) -> Option<&ConnectionTls> {
        self.tls.as_ref()
    }
    pub fn timeout(&self) -> Duration {
        Duration::from_secs(self.timeout)
    }

    fn ensure(mut self, auth: Option<&Authentication>) -> Self {
        match auth {
            Some(auth) if auth.auth_type() == &AuthType::Integrated => {
                self.hostname = "localhost".to_string().into();
                self.fail_over_partner = None;
                self.socket = None;
            }
            _ => {}
        }
        self
    }
}

impl Default for Connection {
    fn default() -> Self {
        Self {
            hostname: defaults::CONNECTION_HOST_NAME.to_string().into(),
            fail_over_partner: None,
            port: Port(defaults::CONNECTION_PORT),
            socket: None,
            tls: None,
            timeout: defaults::CONNECTION_TIMEOUT,
        }
    }
}

#[derive(PartialEq, Debug, Clone)]
pub struct ConnectionTls {
    ca: PathBuf,
    client_certificate: PathBuf,
}

impl ConnectionTls {
    pub fn from_yaml(yaml: &Yaml) -> Result<Option<Self>> {
        let tls = yaml.get(keys::TLS);
        if tls.is_badvalue() {
            return Ok(None);
        }
        Ok(Some(Self {
            ca: tls.get_pathbuf(keys::CA).context("Bad/Missing CA")?,
            client_certificate: tls
                .get_pathbuf(keys::CLIENT_CERTIFICATE)
                .context("bad/Missing CLIENT_CERTIFICATE")?,
        }))
    }
    pub fn ca(&self) -> &Path {
        &self.ca
    }
    pub fn client_certificate(&self) -> &Path {
        &self.client_certificate
    }
}

#[derive(PartialEq, Debug, Clone, Default)]
pub struct Endpoint {
    auth: Authentication,
    conn: Connection,
}

impl Endpoint {
    pub fn new(auth: &Authentication, conn: &Connection) -> Self {
        Self {
            auth: auth.clone(),
            conn: conn.clone(),
        }
    }
    pub fn auth(&self) -> &Authentication {
        &self.auth
    }

    pub fn conn(&self) -> &Connection {
        &self.conn
    }

    pub fn port(&self) -> Port {
        self.conn.port()
    }

    pub fn split(&self) -> (&Authentication, &Connection) {
        (self.auth(), self.conn())
    }

    pub fn hostname(&self) -> HostName {
        if self.auth().auth_type() == &AuthType::Integrated {
            "localhost".to_string().into()
        } else {
            self.conn().hostname().clone()
        }
    }
}

#[derive(PartialEq, Debug, Clone)]
pub struct Discovery {
    detect: bool,
    include: Vec<String>,
    exclude: Vec<String>,
}

impl Default for Discovery {
    fn default() -> Self {
        Self {
            detect: defaults::DISCOVERY_DETECT,
            include: vec![],
            exclude: vec![],
        }
    }
}

impl Discovery {
    pub fn from_yaml(yaml: &Yaml) -> Result<Option<Self>> {
        let discovery = yaml.get(keys::DISCOVERY);
        if discovery.is_badvalue() {
            return Ok(None);
        }
        Ok(Some(Self {
            detect: discovery.get_bool(keys::DETECT, defaults::DISCOVERY_DETECT),
            include: discovery.get_string_vector(keys::INCLUDE, &[]),
            exclude: discovery.get_string_vector(keys::EXCLUDE, &[]),
        }))
    }
    pub fn detect(&self) -> bool {
        self.detect
    }
    pub fn include(&self) -> &Vec<String> {
        &self.include
    }
    pub fn exclude(&self) -> &Vec<String> {
        &self.exclude
    }
}

#[derive(PartialEq, Debug, Clone)]
pub enum Mode {
    Port,
    Socket,
    Special,
}

impl Mode {
    pub fn from_yaml(yaml: &Yaml) -> Result<Self> {
        Mode::try_from(yaml.get_string(keys::MODE).as_deref().unwrap_or_default())
    }
}

impl TryFrom<&str> for Mode {
    type Error = anyhow::Error;

    fn try_from(str: &str) -> Result<Self> {
        match str::to_ascii_lowercase(str).as_ref() {
            values::PORT => Ok(Mode::Port),
            values::SOCKET => Ok(Mode::Socket),
            values::SPECIAL => Ok(Mode::Special),
            _ => Err(anyhow!("unsupported mode")),
        }
    }
}

#[derive(PartialEq, Debug, Clone)]
pub struct CustomInstance {
    /// also known as sid
    name: InstanceName,
    auth: Authentication,
    conn: Connection,
    alias: Option<InstanceAlias>,
    piggyback: Option<Piggyback>,
}

impl CustomInstance {
    pub fn from_yaml(
        yaml: &Yaml,
        main_auth: &Authentication,
        main_conn: &Connection,
        sections: &Sections,
    ) -> Result<Self> {
        let name = InstanceName::from(
            yaml.get_string(keys::SID)
                .context("Bad/Missing sid in instance")?
                .to_uppercase(),
        );
        let (auth, conn) = CustomInstance::make_auth_and_conn(yaml, main_auth, main_conn, &name)?;
        Ok(Self {
            name,
            auth,
            conn,
            alias: yaml.get_string(keys::ALIAS).map(InstanceAlias::from),
            piggyback: Piggyback::from_yaml(yaml, sections)?,
        })
    }

    /// Make auth and conn for custom instance using yaml
    /// - fallback on main_auth and main_conn if not defined in yaml
    /// - correct connection hostname if needed
    fn make_auth_and_conn(
        yaml: &Yaml,
        main_auth: &Authentication,
        main_conn: &Connection,
        sid: &InstanceName,
    ) -> Result<(Authentication, Connection)> {
        let mut auth = Authentication::from_yaml(yaml).unwrap_or(main_auth.clone());
        let mut conn = Connection::from_yaml(yaml, Some(&auth))?.unwrap_or(main_conn.clone());

        let instance_host = calc_real_host(&auth, &conn);
        let main_host = calc_real_host(main_auth, main_conn);
        if instance_host != main_host {
            log::error!("Host {instance_host} defined in {sid} doesn't match to main host {main_host}. Try to fall back");
            if main_auth.auth_type() == auth.auth_type()
                || main_auth.auth_type() == &AuthType::Integrated
            {
                log::warn!("Fall back to main conn host {main_host}");
                conn = Connection {
                    hostname: main_host,
                    ..conn
                };
            } else if auth.auth_type() == &AuthType::Integrated {
                log::warn!(
                    "Instance auth is `integrated`, but not main auth: fall back to main auth {:?}",
                    main_auth.auth_type()
                );
                auth = main_auth.clone();
            } else {
                log::error!(
                    "Fall back is impossible {:?} {:?}",
                    main_auth.auth_type(),
                    auth.auth_type()
                );
            }
        }
        if auth.auth_type() == &AuthType::Integrated {
            conn = Connection {
                hostname: "localhost".to_string().into(),
                ..conn
            };
        }
        Ok((auth, conn))
    }

    /// also known as sid
    pub fn name(&self) -> &InstanceName {
        &self.name
    }
    pub fn auth(&self) -> &Authentication {
        &self.auth
    }
    pub fn conn(&self) -> &Connection {
        &self.conn
    }
    pub fn endpoint(&self) -> Endpoint {
        Endpoint::new(&self.auth, &self.conn)
    }
    pub fn alias(&self) -> &Option<InstanceAlias> {
        &self.alias
    }
    pub fn piggyback(&self) -> Option<&Piggyback> {
        self.piggyback.as_ref()
    }
    pub fn calc_real_host(&self) -> HostName {
        calc_real_host(&self.auth, &self.conn)
    }
}

pub fn calc_real_host(auth: &Authentication, conn: &Connection) -> HostName {
    if auth.auth_type() == &AuthType::Integrated {
        "localhost".to_string().into()
    } else {
        conn.hostname().clone()
    }
}

#[derive(PartialEq, Debug, Clone)]
pub struct Piggyback {
    hostname: String,
    sections: Sections,
}

impl Piggyback {
    pub fn from_yaml(yaml: &Yaml, sections: &Sections) -> Result<Option<Self>> {
        let piggyback = yaml.get(keys::PIGGYBACK);
        if piggyback.is_badvalue() {
            return Ok(None);
        }
        Ok(Some(Self {
            hostname: piggyback
                .get_string(keys::HOSTNAME)
                .context("Bad/Missing hostname in piggyback")?,
            sections: Sections::from_yaml(piggyback, sections)?,
        }))
    }

    pub fn hostname(&self) -> &String {
        &self.hostname
    }

    pub fn sections(&self) -> &Sections {
        &self.sections
    }
}

#[cfg(test)]
mod tests {
    use tests::defaults::{MAX_CONNECTIONS, MAX_QUERIES};

    use self::data::TEST_CONFIG;

    use super::*;
    use crate::config::{section::SectionKind, yaml::test_tools::create_yaml};
    mod data {
        /// copied from tests/files/test-config.yaml
        pub const TEST_CONFIG: &str = r#"
---
mssql:
  main: # mandatory, to be used if no specific config
    options:
      max_connections: 5
    authentication: # mandatory
      username: "foo" # mandatory
      password: "bar" # optional
      type: "sql_server" # optional, default: "integrated", values: sql_server, windows, token and integrated (current windows user) 
      access_token: "baz" # optional
    connection: # optional
      hostname: "localhost" # optional(default: "localhost")
      failoverpartner: "localhost2" # optional
      port: 1433 # optional(default: 1433)
      socket: 'C:\path\to\file' # optional
      tls: # optional
        ca: 'C:\path\to\file' # mandatory
        client_certificate: 'C:\path\to\file' # mandatory
      timeout: 5 # optional(default: 5)
    sections: # optional
    - instance:  # special section
    - databases:
    - counters:
    - blocked_sessions:
    - transactionlogs:
    - clusters:
    - mirroring:
    - availability_groups:
    - connections:
    - tablespaces:
        is_async : yes
    - datafiles:
        is_async: yes
    - backup:
        is_async: yes
    - jobs:
        is_async: yes
    - someOtherSQL:
        is_async: yes
        disabled: yes
    cache_age: 600 # optional(default:600)
    piggyback_host: "my_pb_host"
    discovery: # optional
      detect: true # optional(default:yes)
      include: ["foo", "bar"] # optional prio 2; use instance even if excluded
      exclude: ["baz"] # optional, prio 3
    mode: "socket" # optional(default:"port") - "socket", "port" or "special"
    instances: # optional
      - sid: "INST1" # mandatory
        authentication: # optional, same as above
        connection: # optional,  same as above
        alias: "someApplicationName" # optional
        piggyback: # optional
          hostname: "myPiggybackHost" # mandatory
          sections: # optional, same as above
      - sid: "INST2" # mandatory
  configs:
    - main:
        options:
          max_connections: 11
        authentication: # mandatory
          username: "f" # mandatory
          password: "b"
          type: "sql_server"
        connection: # optional
          hostname: "localhost" # optional(default: "localhost")
          timeout: 5 # optional(default: 5)
        discovery: # optional
          detect: yes # optional(default:yes)
    - main:
        options:
          max_connections: 11
        connection: # optional
          hostname: "localhost" # optional(default: "localhost")
          timeout: 5 # optional(default: 5)
        piggyback_host: "no"
        discovery: # optional
          detect: yes # optional(default:yes)
    - main:
        authentication: # optional
          username: "f"
          password: "b"
          type: "sql_server"
  "#;
        pub const AUTHENTICATION_FULL: &str = r#"
authentication:
  username: "foo"
  password: "bar"
  type: "sql_server"
  access_token: "baz"
"#;
        #[cfg(windows)]
        pub const AUTHENTICATION_INTEGRATED: &str = r#"
authentication:
  username: "foo"
  password: "bar"
  type: "integrated"
  access_token: "baz"
"#;
        pub const AUTHENTICATION_MINI: &str = r#"
authentication:
  username: "foo"
  _password: "bar"
  _type: "system"
  _access_token: "baz"
"#;

        pub const CONNECTION_FULL: &str = r#"
connection:
  hostname: "alice"
  failoverpartner: "bob"
  port: 9999
  socket: 'C:\path\to\file_socket'
  tls:
    ca: 'C:\path\to\file_ca'
    client_certificate: 'C:\path\to\file_client'
  timeout: 341
"#;
        pub const DISCOVERY_FULL: &str = r#"
discovery:
  detect: false
  include: ["a", "b" ]
  exclude: ["c", "d" ]
"#;
        pub const PIGGYBACK_HOST: &str = "piggyback_host: zuzu";

        pub const PIGGYBACK_FULL: &str = r#"
piggyback:
  hostname: "piggy_host"
  sections:
    - alw1:
    - alw2:
    - cached1:
        is_async: yes
    - cached2:
        is_async: yes
    - disabled:
        disabled: yes
  cache_age: 111
"#;
        pub const PIGGYBACK_SHORT: &str = r#"
piggyback:
  hostname: "piggy_host"
"#;
        pub const INSTANCE: &str = r#"
sid: "INST1"
authentication:
  username: "u1"
  type: "sql_server"
connection:
  hostname: "h1"
alias: "a1"
piggyback:
  hostname: "piggy"
  sections:
  cache_age: 123
"#;
        pub const PIGGYBACK_NO_HOSTNAME: &str = r#"
piggyback:
  _hostname: "piggy_host"
  sections:
    cache_age: 111
"#;
        pub const PIGGYBACK_NO_SECTIONS: &str = r#"
piggyback:
  hostname: "piggy_host"
  _sections:
    cache_age: 111
"#;
    }

    #[test]
    fn test_config_default() {
        assert_eq!(
            Config::default(),
            Config {
                auth: Authentication::default(),
                conn: Connection::default(),
                sections: Sections::default(),
                discovery: Discovery::default(),
                piggyback_host: None,
                mode: Mode::Port,
                custom_instances: vec![],
                configs: vec![],
                hash: String::new(),
                options: Options::default(),
            }
        );
    }

    #[test]
    fn test_system_default() {
        let s = Options::default();
        assert_eq!(s.max_connections(), MAX_CONNECTIONS.into());
        assert_eq!(s.max_queries(), MAX_QUERIES.into());
    }

    #[test]
    fn test_config_inheritance() {
        let c = Config::from_string(data::TEST_CONFIG).unwrap().unwrap();
        assert_eq!(c.configs.len(), 3);
        assert_eq!(c.custom_instances.len(), 2);
        assert_eq!(c.configs[0].options(), &Options::new(11.into()));
        assert_eq!(c.configs[1].options(), &Options::new(11.into()));
        assert_eq!(c.configs[1].auth(), c.auth());
        assert_ne!(c.configs[1].conn(), c.conn());
        assert_ne!(c.configs[1].discovery(), c.discovery());
        assert_ne!(c.configs[1].options(), c.options());
        assert_ne!(c.configs[1].piggyback_host(), c.piggyback_host());
        assert_ne!(c.configs[2].auth(), c.auth());
        assert_eq!(c.configs[2].conn(), c.conn());
        assert_eq!(c.configs[2].discovery(), c.discovery());
        assert_eq!(c.configs[2].options(), c.options());
        assert_eq!(c.configs[2].sections(), c.sections());
        assert_eq!(c.configs[2].mode(), c.mode());

        // NON INHERITED
        assert_eq!(c.configs[2].piggyback_host(), None);
        assert_ne!(c.configs[2].piggyback_host(), c.piggyback_host());
        assert_ne!(c.configs[2].instances(), c.instances());
    }

    #[test]
    fn test_authentication_from_yaml() {
        let a = Authentication::from_yaml(&create_yaml(data::AUTHENTICATION_FULL)).unwrap();
        assert_eq!(a.username(), "foo");
        assert_eq!(a.password(), Some(&"bar".to_owned()));
        assert_eq!(a.auth_type(), &AuthType::SqlServer);
        assert_eq!(a.access_token(), Some(&"baz".to_owned()));
    }

    #[test]
    fn test_authentication_from_yaml_empty() {
        assert!(Authentication::from_yaml(&create_yaml(r"authentication:")).is_ok());
    }

    #[test]
    fn test_authentication_from_yaml_no_username() {
        assert!(Authentication::from_yaml(&create_yaml(
            r#"
authentication:
  _username: 'aa'
"#
        ))
        .is_ok());
    }

    #[test]
    fn test_authentication_from_yaml_mini() {
        let a = Authentication::from_yaml(&create_yaml(data::AUTHENTICATION_MINI)).unwrap();
        #[cfg(windows)]
        assert_eq!(a.username(), "");
        #[cfg(unix)]
        assert_eq!(a.username(), "foo");
        assert_eq!(a.password(), None);
        #[cfg(windows)]
        assert_eq!(a.auth_type(), &AuthType::Integrated);
        #[cfg(unix)]
        assert_eq!(a.auth_type(), &AuthType::SqlServer);
        assert_eq!(a.access_token(), None);
    }

    #[cfg(windows)]
    #[test]
    fn test_authentication_from_yaml_integrated() {
        let a = Authentication::from_yaml(&create_yaml(data::AUTHENTICATION_INTEGRATED)).unwrap();
        assert_eq!(a.username(), "");
        assert_eq!(a.password(), None);
        assert_eq!(a.auth_type(), &AuthType::Integrated);
        assert_eq!(a.access_token(), None);
    }

    #[test]
    fn test_connection_from_yaml() {
        let c = Connection::from_yaml(&create_yaml(data::CONNECTION_FULL), None)
            .unwrap()
            .unwrap();
        assert_eq!(c.hostname(), &"alice".to_string().into());
        assert_eq!(c.fail_over_partner(), Some(&"bob".to_owned()));
        assert_eq!(c.port(), Port(9999));
        assert_eq!(c.socket(), Some(&PathBuf::from(r"C:\path\to\file_socket")));
        assert_eq!(c.timeout(), Duration::from_secs(341));
        let tls = c.tls().unwrap();
        assert_eq!(tls.ca(), PathBuf::from(r"C:\path\to\file_ca"));
        assert_eq!(
            tls.client_certificate(),
            PathBuf::from(r"C:\path\to\file_client")
        );
    }

    #[cfg(windows)]
    #[test]
    fn test_connection_from_yaml_auth_integrated() {
        let a = Authentication::from_yaml(&create_yaml(data::AUTHENTICATION_INTEGRATED)).unwrap();
        let c = Connection::from_yaml(&create_yaml(data::CONNECTION_FULL), Some(&a))
            .unwrap()
            .unwrap();
        assert_eq!(c.hostname(), &"localhost".to_string().into());
        assert_eq!(c.fail_over_partner(), None);
        assert_eq!(c.port(), Port(9999));
        assert_eq!(c.socket(), None);
        assert_eq!(c.timeout(), Duration::from_secs(341));
        let tls = c.tls().unwrap();
        assert_eq!(tls.ca(), PathBuf::from(r"C:\path\to\file_ca"));
        assert_eq!(
            tls.client_certificate(),
            PathBuf::from(r"C:\path\to\file_client")
        );
    }

    #[test]
    fn test_connection_from_yaml_default() {
        assert_eq!(
            Connection::from_yaml(&create_connection_yaml_default(), None)
                .unwrap()
                .unwrap(),
            Connection::default()
        );
        assert_eq!(
            Connection::from_yaml(&create_yaml("nothing: "), None).unwrap(),
            None
        );
    }

    fn create_connection_yaml_default() -> Yaml {
        const SOURCE: &str = r#"
connection:
  _nothing: "nothing"
"#;
        create_yaml(SOURCE)
    }

    #[test]
    fn test_discovery_from_yaml_full() {
        let discovery = Discovery::from_yaml(&create_yaml(data::DISCOVERY_FULL))
            .unwrap()
            .unwrap();
        assert!(!discovery.detect());
        assert_eq!(discovery.include(), &vec!["a".to_string(), "b".to_string()]);
        assert_eq!(discovery.exclude(), &vec!["c".to_string(), "d".to_string()]);
    }

    #[test]
    fn test_piggyback_host() {
        let ph = &create_yaml(data::PIGGYBACK_HOST).get_string(keys::PIGGYBACK_HOST);
        assert_eq!(ph.as_deref(), Some("zuzu"));
    }

    #[test]
    fn test_discovery_from_yaml_default() {
        let discovery = Discovery::from_yaml(&create_discovery_yaml_default())
            .unwrap()
            .unwrap();
        assert!(discovery.detect());
        assert!(discovery.include().is_empty());
        assert!(discovery.exclude().is_empty());
    }

    fn create_discovery_yaml_default() -> Yaml {
        const SOURCE: &str = r#"
discovery:
  _nothing: "nothing"
"#;
        create_yaml(SOURCE)
    }

    #[test]
    fn test_mode_try_from() {
        assert!(Mode::try_from("a").is_err());
        assert_eq!(Mode::try_from("poRt").unwrap(), Mode::Port);
        assert_eq!(Mode::try_from("soCKET").unwrap(), Mode::Socket);
        assert_eq!(Mode::try_from("SPecial").unwrap(), Mode::Special);
    }

    #[test]
    fn test_mode_from_yaml() {
        assert!(Mode::from_yaml(&create_yaml("mode: Zu")).is_err());
        assert!(Mode::from_yaml(&create_yaml("no_mode: port")).is_err());
        assert_eq!(
            Mode::from_yaml(&create_yaml("mode: Special")).unwrap(),
            Mode::Special
        );
    }

    fn as_names(sections: Vec<&Section>) -> Vec<&str> {
        sections.iter().map(|s| s.name()).collect()
    }

    #[test]
    fn test_piggyback() {
        let piggyback =
            Piggyback::from_yaml(&create_yaml(data::PIGGYBACK_FULL), &Sections::default())
                .unwrap()
                .unwrap();
        assert_eq!(piggyback.hostname(), "piggy_host");
        let all = piggyback.sections();
        assert_eq!(as_names(all.select(&[SectionKind::Sync])), ["alw1", "alw2"],);
        assert_eq!(
            as_names(all.select(&[SectionKind::Async])),
            ["cached1", "cached2"]
        );
        assert_eq!(as_names(all.select(&[SectionKind::Disabled])), ["disabled"]);
    }

    #[test]
    fn test_piggyback_short() {
        let piggyback =
            Piggyback::from_yaml(&create_yaml(data::PIGGYBACK_SHORT), &Sections::default())
                .unwrap()
                .unwrap();
        assert_eq!(piggyback.hostname(), "piggy_host");
        let all = piggyback.sections();
        assert_eq!(Sections::default(), all.clone());
    }

    #[test]
    fn test_piggyback_error() {
        assert!(Piggyback::from_yaml(
            &create_yaml(data::PIGGYBACK_NO_HOSTNAME),
            &Sections::default()
        )
        .is_err());
        assert_eq!(
            Piggyback::from_yaml(
                &create_yaml(data::PIGGYBACK_NO_SECTIONS),
                &Sections::default()
            )
            .unwrap()
            .unwrap()
            .sections(),
            &Sections::default()
        );
    }

    #[test]
    fn test_piggyback_none() {
        assert_eq!(
            Piggyback::from_yaml(&create_yaml("source:\n  xxx"), &Sections::default()).unwrap(),
            None
        );
    }
    #[test]
    fn test_custom_instance() {
        let a = Authentication {
            username: "ux".to_string(),
            auth_type: AuthType::SqlServer,
            ..Default::default()
        };
        let instance = CustomInstance::from_yaml(
            &create_yaml(data::INSTANCE),
            &a,
            &Connection::default(),
            &Sections::default(),
        )
        .unwrap();
        assert_eq!(instance.name().to_string(), "INST1");
        assert_eq!(instance.auth().username(), "u1");
        assert_eq!(instance.conn().hostname(), &"localhost".to_string().into());
        assert_eq!(instance.calc_real_host(), "localhost".to_string().into());
        assert_eq!(instance.alias(), &Some("a1".to_string().into()));
        assert_eq!(instance.piggyback().unwrap().hostname(), "piggy");
        assert_eq!(instance.piggyback().unwrap().sections().cache_age(), 123);
    }

    #[cfg(windows)]
    #[test]
    fn test_custom_instance_integrated() {
        pub const INSTANCE_INTEGRATED: &str = r#"
sid: "INST1"
authentication:
  username: "u1"
  auth_type: "integrated"
connection:
  hostname: "h1"
"#;
        let instance = CustomInstance::from_yaml(
            &create_yaml(INSTANCE_INTEGRATED),
            &Authentication::default(),
            &Connection::default(),
            &Sections::default(),
        )
        .unwrap();
        assert_eq!(instance.name().to_string(), "INST1");
        assert_eq!(instance.auth().username(), "");
        assert_eq!(instance.conn().hostname(), &"localhost".to_string().into());
        assert_eq!(instance.calc_real_host(), "localhost".to_string().into());
    }

    #[test]
    fn test_config() {
        let c = Config::from_string(data::TEST_CONFIG).unwrap().unwrap();
        assert_eq!(c.options(), &Options::new(5.into()));
        assert_eq!(c.instances().len(), 2);
        assert!(c.instances()[0].piggyback().is_some());
        assert_eq!(
            c.instances()[0].piggyback().unwrap().hostname(),
            "myPiggybackHost"
        );
        assert_eq!(c.instances()[0].name().to_string(), "INST1");
        assert_eq!(c.instances()[1].name().to_string(), "INST2");
        assert_eq!(c.mode(), &Mode::Socket);
        assert_eq!(
            c.discovery().include(),
            &vec!["foo".to_string(), "bar".to_string()]
        );
        assert_eq!(c.discovery().exclude(), &vec!["baz".to_string()]);
        assert!(c.discovery().detect());
        assert_eq!(c.auth().username(), "foo");
        assert_eq!(c.auth().password().unwrap(), "bar");
        assert_eq!(c.auth().auth_type(), &AuthType::SqlServer);
        assert_eq!(c.auth().access_token().unwrap(), "baz");
        assert_eq!(c.conn().hostname(), &"localhost".to_string().into());
        assert_eq!(c.conn().fail_over_partner().unwrap(), "localhost2");
        assert_eq!(c.conn().port(), Port(defaults::CONNECTION_PORT));
        assert_eq!(
            c.conn().socket().unwrap(),
            &PathBuf::from(r"C:\path\to\file")
        );
        assert_eq!(c.piggyback_host(), Some("my_pb_host"));
        assert_eq!(c.conn().tls().unwrap().ca(), Path::new(r"C:\path\to\file"));
        assert_eq!(
            c.conn().tls().unwrap().client_certificate(),
            Path::new(r"C:\path\to\file")
        );
        assert_eq!(
            c.conn().timeout(),
            std::time::Duration::from_secs(defaults::CONNECTION_TIMEOUT)
        );
        let as_names = |sections: &[Section], kind: SectionKind| {
            sections
                .iter()
                .filter(|s| s.kind() == kind)
                .map(|s| s.name().to_string())
                .collect::<Vec<String>>()
        };
        assert_eq!(
            as_names(c.all_sections(), SectionKind::Sync),
            defaults::SECTIONS_ALWAYS
        );
        assert_eq!(
            as_names(c.all_sections(), SectionKind::Async),
            defaults::SECTIONS_CACHED
        );
        assert_eq!(
            as_names(c.all_sections(), SectionKind::Disabled),
            ["someOtherSQL".to_string()]
        );
        assert_eq!(c.cache_age(), defaults::SECTIONS_CACHE_AGE);
    }

    #[test]
    fn test_config_discovery() {
        let c = make_detect_config(&[], &[]);
        assert!(c.is_instance_allowed(&"weird"));
        let c = make_detect_config(&["a", "b"], &["a", "b"]);
        assert!(!c.is_instance_allowed(&"weird"));
        assert!(c.is_instance_allowed(&"a"));
        assert!(c.is_instance_allowed(&"b"));
    }

    fn make_detect_config(include: &[&str], exclude: &[&str]) -> Config {
        let source = format!(
            r"---
mssql:
  main:
    authentication:
      username: foo
    discovery:
      detect: true # doesn't matter for us
      include: {include:?}
      exclude: {exclude:?}
    instances:
      - sid: sid1
      - sid: sid2
        connection:
          hostname: ab
"
        );
        Config::from_string(&source).unwrap().unwrap()
    }

    #[test]
    fn test_calc_hash() {
        let c1 = Config::from_string(TEST_CONFIG).unwrap().unwrap();
        let c2 = Config::from_string(&(TEST_CONFIG.to_string() + "\n# xxx"))
            .unwrap()
            .unwrap();
        let c3 = Config::from_string(
            &(TEST_CONFIG.to_string()
                + r#"
    - main:
        authentication: # mandatory
          username: "f" # mandatory"#),
        )
        .unwrap()
        .unwrap();
        assert_eq!(c1.hash.len(), 16);
        assert_eq!(c1.hash, c2.hash);
        assert_ne!(c1.hash, c3.hash);
    }

    #[test]
    fn test_calc_effective_host() {
        let conn_to_bar = Connection {
            hostname: "bAr".to_string().into(),
            ..Default::default()
        };
        let auth_integrated = Authentication {
            auth_type: AuthType::Integrated,
            ..Default::default()
        };
        let auth_sql_server = Authentication {
            auth_type: AuthType::SqlServer,
            ..Default::default()
        };

        assert_eq!(
            calc_real_host(&auth_integrated, &conn_to_bar),
            "localhost".to_string().into()
        );
        assert_eq!(
            calc_real_host(&auth_sql_server, &conn_to_bar),
            "bAr".to_string().into()
        );
    }

    #[test]
    fn test_sections_enabled() {
        const CONFIG: &str = r#"
---
mssql:
  main: # mandatory, to be used if no specific config
    authentication: # mandatory
      username: "f" # mandatory
    sections:
      - instance:
      - jobs:
          is_async: yes
      - backup:
          disabled: yes
"#;
        let config = Config::from_string(CONFIG).unwrap().unwrap();
        assert_eq!(
            config
                .all_sections()
                .iter()
                .map(|s| (s.name(), s.kind()))
                .collect::<Vec<(&str, SectionKind)>>(),
            [
                ("instance", SectionKind::Sync),
                ("jobs", SectionKind::Async),
                ("backup", SectionKind::Disabled),
            ]
        );
        assert_eq!(
            config
                .valid_sections()
                .iter()
                .map(|s| (s.name(), s.kind()))
                .collect::<Vec<(&str, SectionKind)>>(),
            [
                ("instance", SectionKind::Sync),
                ("jobs", SectionKind::Async),
            ]
        );
    }
}
