vcl 4.1;

backend default {
    .host = "photo-service";
    .port = "80";
}

sub vcl_recv {
    if (req.url ~ "^/static/") {
        unset req.http.Cookie;      # public : le cookie de session ne doit pas empêcher le cache
        return (hash);              # on cherche dans le cache
    }
    return (pass);                  # tout le reste : jamais de cache (réponses privées, état de l'application)
}

sub vcl_backend_response {
    if (bereq.url ~ "^/static/" && beresp.status == 200) {
        unset beresp.http.Set-Cookie;
        set beresp.http.Cache-Control = "public, max-age=300";
        set beresp.ttl = 5m;
        return (deliver);           # on garde 5 minutes, sans appliquer les règles prudentes par défaut
    }
}