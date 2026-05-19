pipeline {
    agent any
    parameters {
        choice(
            name: 'AMBIENTE',
            choices: ['homolog', 'prod'],
            description: 'Ambiente a ser atualizado'
        )
    }
    stages {
        stage('Deploy') {
            steps {
                dir('/home/univates/aurum-fintech') {
                    sh "chmod +x deploy-${params.AMBIENTE}.sh && ./deploy-${params.AMBIENTE}.sh"
                }
            }
        }
    }
    post {
        success { echo "Deploy em ${params.AMBIENTE} concluido com sucesso." }
        failure  { echo "Falha no deploy em ${params.AMBIENTE}." }
    }
}
