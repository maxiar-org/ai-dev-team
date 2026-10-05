// @ts-check
import { defineConfig } from 'astro/config';
import starlight from '@astrojs/starlight';
import mermaid from 'astro-mermaid';

// https://astro.build/config
export default defineConfig({
	site: 'https://maxiar-org.github.io',
	base: '/ai-dev-team/',
	integrations: [
		mermaid({
			theme: 'neutral',
			autoTheme: true,
		}),
		starlight({
			title: 'AI Dev Team',
			description: 'El framework de agentes de IA que desarrolla sobre los repos de maxiar-org.',
			locales: {
				root: { label: 'Español', lang: 'es' },
			},
			social: [{ icon: 'github', label: 'GitHub', href: 'https://github.com/maxiar-org/ai-dev-team' }],
			editLink: {
				baseUrl: 'https://github.com/maxiar-org/ai-dev-team/edit/main/docs/',
			},
			sidebar: [
				{ label: 'Guía', items: [{ autogenerate: { directory: 'guia' } }] },
				{ label: 'Piloto', items: [{ autogenerate: { directory: 'piloto' } }] },
			],
		}),
	],
});
