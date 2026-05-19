import jenkins.model.*
import org.jenkinsci.plugins.workflow.job.WorkflowJob
import org.jenkinsci.plugins.workflow.cps.CpsFlowDefinition
import hudson.model.ParametersDefinitionProperty
import hudson.model.ChoiceParameterDefinition

def jenkins = Jenkins.getInstance()

if (jenkins.getItem('Deploy Aurum') == null) {
    def job = jenkins.createProject(WorkflowJob, 'Deploy Aurum')

    def paramDef = new ChoiceParameterDefinition('AMBIENTE', ['homolog', 'prod'], 'Ambiente a ser atualizado')
    job.addProperty(new ParametersDefinitionProperty([paramDef]))

    def script = '''pipeline {
    agent any
    parameters {
        choice(name: 'AMBIENTE', choices: ['homolog', 'prod'], description: 'Ambiente a ser atualizado')
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
        failure  { echo "Deploy em ${params.AMBIENTE} falhou." }
    }
}'''

    job.setDefinition(new CpsFlowDefinition(script, true))
    job.save()

    println "Job 'Deploy Aurum' criado com sucesso."
}

jenkins.save()
