<script setup lang="ts">
import type { NavigationMenuItem } from "@nuxt/ui";
import { useIntervalFn, useWebSocket } from "@vueuse/core";

const isConnected = ref(false);

const ws = useAppWebSocket();

const unlistenOnConnected = ws.onConnected(() => {
  isConnected.value = true
})

const unlistenOnDisconnected = ws.onDisconnected(() => {
  isConnected.value = false
})

const route = useRoute();

const items = computed<NavigationMenuItem[]>(() => []);

onUnmounted(() => {
	unlistenOnConnected()
	unlistenOnDisconnected()
})
</script>

<template>
  <UHeader>
    <template #title>
      <Logo class="h-6 w-auto" />
    </template>

    <UNavigationMenu :items="items" />

    <template #right>
      <div class="flex flex-row gap-x-2 items-center">
        <div
          class="w-2 h-2 animate-pulse rounded-full"
          :class="{ 'bg-green-400': isConnected, 'bg-red-400': !isConnected }"
        />

        <p
          :class="{
            'text-green-400': isConnected,
            'text-red-400': !isConnected,
          }"
        >
          {{ isConnected ? "connected" : "disconnected" }}
        </p>
      </div>
    </template>
  </UHeader>
</template>
