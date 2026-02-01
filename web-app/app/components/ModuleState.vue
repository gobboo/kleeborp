<script setup lang="ts">
import { useWebSocket } from "@vueuse/core";

const ws = useAppWebSocket();

const onWsConnected = ws.onConnected((ws) => {
  ws.send(JSON.stringify({ command: "get_state" }));
});

onUnmounted(async () => {
  onWsConnected()
});
</script>

<template>
	<pre>
		{{ ws.data }}
	</pre>
</template>
