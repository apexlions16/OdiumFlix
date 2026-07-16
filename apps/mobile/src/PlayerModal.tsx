import React from 'react';
import {Modal,Pressable,SafeAreaView,StatusBar,Text,View} from 'react-native';
import {VideoView,useVideoPlayer} from 'expo-video';
import type {Item} from './catalog';
import {s} from './styles';
export const PlayerModal=({item,onClose}:{item:Item;onClose:()=>void})=>{const source=item.playbackMode==='hls'?{uri:item.playbackUrl!,contentType:'hls' as const}:{uri:item.playbackUrl!};const player=useVideoPlayer(source,instance=>instance.play());return<Modal visible animationType="fade" onRequestClose={onClose}><SafeAreaView style={s.playerRoot}><StatusBar hidden/><VideoView player={player} style={s.video} nativeControls contentFit="contain"/><Pressable style={s.playerClose} onPress={onClose}><Text style={s.playerCloseText}>×</Text></Pressable><View style={s.playerTitle}><Text style={s.playerTitleText}>{item.title}</Text><Text style={s.muted}>{item.qualities.join(' · ')}</Text></View></SafeAreaView></Modal>;};
