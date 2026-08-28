<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { REALTIME_EVENT, type RealtimeEvent } from '../services/realtime'
import RepositoryDetailView from './RepositoryDetailView.vue'

const route = useRoute()
const revision = ref(0)
let timer:number|undefined

function handleRealtime(event:Event):void {
  const detail=(event as CustomEvent<RealtimeEvent>).detail
  if(!detail||!detail.type.startsWith('github.'))return
  if(detail.repository_id&&detail.repository_id!==String(route.params.id))return
  window.clearTimeout(timer)
  timer=window.setTimeout(()=>{revision.value+=1},100)
}

onMounted(()=>window.addEventListener(REALTIME_EVENT,handleRealtime))
onBeforeUnmount(()=>{window.removeEventListener(REALTIME_EVENT,handleRealtime);window.clearTimeout(timer)})
</script>

<template>
  <RepositoryDetailView :key="`${String(route.params.id)}:${revision}`" />
</template>
