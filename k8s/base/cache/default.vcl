vcl 4.1;

backend default {
    .host = "photo-service";
    .port = "80";
}

sub vcl_recv {
    if (req.url ~ "^/(health)?$") {
        return (pass);
    }
}