# EA Explorer's own draw.io (phase 28, D354, D396): the published draw.io image plus our plugin for drawn views. draw.io's
# own ArchiMate drawings are reused for the glyphs; its shape libraries are switched off from EA Explorer (embed mode).
ARG DRAWIO_IMAGE=jgraph/drawio:32.6.10
FROM ${DRAWIO_IMAGE}
COPY eax-plugin.js $CATALINA_HOME/webapps/draw/plugins/eax.js
# Loaded from index.html (the image's start script rewrites PostConfig.js, so not from there); the plugin acts only in
# embed mode with eax=1, that is inside EA Explorer
RUN sed -i 's#</body>#<script src="plugins/eax.js"></script></body>#' $CATALINA_HOME/webapps/draw/index.html \
 && grep -q 'plugins/eax.js' $CATALINA_HOME/webapps/draw/index.html
